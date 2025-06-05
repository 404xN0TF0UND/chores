import os
import re
from datetime import datetime, timedelta
from flask import request, current_app
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from models import db, Chore, User, ChoreHistory

# --- Dusty's wit ---
import random

DUSTY_SNARK = [
    "Wow, you're actually doing a chore? I'm shocked.",
    "Another one bites the dust. Literally.",
    "Impressive. You’ve done something for once.",
    "If chores were trophies, you'd almost deserve one.",
    "Keep this up and I’ll consider updating your résumé."
]

HOLIDAY_SNARK = {
    "01-01": "New year, same dirty house. Chop chop!",
    "12-25": "Even Santa makes his elves clean up.",
    "07-04": "Time to declare independence from laziness.",
}

# --- Dusty helper ---
def dusty_response(msg):
    resp = MessagingResponse()
    resp.message(f"[Dusty 🤖] {msg}")
    return str(resp)

# --- User utilities ---
def get_user_by_phone(phone):
    return User.query.filter_by(phone=phone).first()

def get_user_by_name(name):
    return User.query.filter(User.name.ilike(name)).first()

def seed_users_from_env():
    for key, value in os.environ.items():
        if key.startswith("USER_"):
            name = key[5:]
            phone = value
            if not User.query.filter_by(phone=phone).first():
                user = User(name=name, phone=phone)
                if name.lower() in ['ronnie', 'becky']:  # mark admins
                    user.is_admin = True
                db.session.add(user)
    db.session.commit()

# --- Chore utilities ---
def get_assigned_chores(user_id):
    return Chore.query.filter_by(assigned_to_id=user_id, completed=False).order_by(Chore.due_date).all()

def get_upcoming_chores(user, days=3):
    now = datetime.now()
    upcoming = now + timedelta(days=days)
    return Chore.query.filter(
        Chore.assigned_to_id == user.id,
        Chore.due_date != None,
        Chore.completed == False,
        Chore.due_date <= upcoming
    ).order_by(Chore.due_date).all()

def get_completed_chores(user):
    return Chore.query.filter_by(assigned_to_id=user.id, completed=True).all()

def complete_chore_by_name(user_id, chore_name):
    chore = Chore.query.filter(
        Chore.assigned_to_id == user_id,
        Chore.name.ilike(f"%{chore_name.strip()}%"),
        Chore.completed == False
    ).first()

    if not chore:
        return None

    chore.completed = True
    chore.completed_at = datetime.utcnow()
    db.session.commit()
    return chore

def list_user_chores(user_id, limit=5):
    chores = Chore.query.filter(
        Chore.assigned_to_id == user_id,
        Chore.completed == False
    ).order_by(Chore.due_date.asc().nullslast()).limit(limit).all()

    result = []
    for chore in chores:
        name = chore.name
        due = chore.due_date.strftime('%Y-%m-%d') if chore.due_date else 'No due date'
        result.append(f"{name} (Due: {due})")
    
    return result

def get_unassigned_chores():
    return Chore.query.filter_by(assigned_to_id=None).all()

def get_chore_history(user=None):
    query = ChoreHistory.query.order_by(ChoreHistory.completed_at.desc())
    if user:
        query = query.filter_by(completed_by_id=user.id)
    return query.all()

def notify_admins(message, twilio_client, from_number):
    admins = User.query.filter_by(is_admin=True).all()
    for admin in admins:
        twilio_client.messages.create(
            body=f"[Dusty Alert] {message}",
            from_=from_number,
            to=admin.phone
        )

# --- Conversation & reminder utilities ---
conversation_state = {}

def clean_conversations(app):
    with app.app_context():
        now = datetime.utcnow()
        to_delete = [k for k, v in conversation_state.items() if now - v['timestamp'] > timedelta(hours=2)]
        for key in to_delete:
            del conversation_state[key]

def send_reminders(app):
    with app.app_context():
        from chores_app import twilio_client
        from_number = os.getenv("TWILIO_NUMBER")
        users = User.query.all()
        now = datetime.now()
        for user in users:
            chores_due = Chore.query.filter(
                Chore.assigned_to_id == user.id,
                Chore.due_date != None,
                Chore.completed == False,
                Chore.due_date.date() == now.date()
            ).all()
            if chores_due:
                message = f"Hey {user.name}, you have {len(chores_due)} chore(s) due today:\n"
                for chore in chores_due:
                    message += f"• {chore.name}\n"
                twilio_client.messages.create(
                    body=message,
                    from_=from_number,
                    to=user.phone
                )

# --- SMS parsing ---
def parse_sms(body):
    body = body.strip().lower()
    if body.startswith("done "):
        return {"intent": "complete", "chore": body[5:].strip()}
    elif body.startswith("add "):
        return {"intent": "add", "raw": body[4:].strip()}
    elif "list" in body:
        return {"intent": "list"}
    return {"intent": "unknown"}

# --- Recurrence parser ---
def parse_recurrence(text):
    text = text.lower()
    if 'daily' in text:
        return 'daily'
    elif 'weekly' in text:
        return 'weekly'
    elif 'monthly' in text:
        return 'monthly'
    elif match := re.search(r'every (\d+)', text):
        return f"every {match.group(1)}"
    return None

# -------SMS ------
def send_sms(to, body):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")

    if not all([account_sid, auth_token, from_number]):
        print("Missing Twilio configuration in environment variables.")
        return

    try:
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=body,
            from_=from_number,
            to=to
        )
        print(f"Sent SMS to {to}: {body}")
    except Exception as e:
        print(f"Failed to send SMS to {to}: {e}")