import os
import re
import random
from datetime import datetime, timedelta
from dateutil import parser as date_parser

from flask import current_app
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client

from models import db, Chore, User, ChoreHistory

# -------------------------------
# Dusty's Snark Arsenal
# -------------------------------
DUSTY_SNARK = [
    "Wow, you're actually doing a chore? I'm shocked.",
    "Another one bites the dust. Literally.",
    "Impressive. You’ve done something for once.",
    "If chores were trophies, you'd almost deserve one.",
    "Keep this up and I’ll consider updating your résumé.",
]

HOLIDAY_SNARK = {
    "01-01": "New year, same dirty house. Chop chop!",
    "07-04": "Time to declare independence from laziness.",
    "12-25": "Even Santa makes his elves clean up.",
}

# -------------------------------
# Response Utilities
# -------------------------------
def dusty_response(msg):
    """Wraps message in Dusty's Twilio voice."""
    resp = MessagingResponse()
    resp.message(f"[Dusty 🤖] {msg}")
    return str(resp)


def get_intent(message):
    text = message.lower().strip()

    if any(kw in text for kw in ['add', 'assign', 'give']):
        return 'add'
    if any(kw in text for kw in ['done', 'complete', 'finished']):
        return 'complete'
    if 'list' in text or 'what are my chores' in text:
        return 'list'
    if 'unassign' in text:
        return 'unassign'
    if text in ['hi', 'hello', 'hey', 'yo']:
        return 'greeting'
    if 'help' in text:
        return 'help'
    return 'unknown'
# -------------------------------
# User Utilities
# -------------------------------
def get_user_by_phone(phone):
    return User.query.filter_by(phone=phone).first()

def get_user_by_name(name):
    return User.query.filter(User.name.ilike(name)).first()

def seed_users_from_env():
    admin_names = os.getenv("ADMINS", "").split(",")
    for key, value in os.environ.items():
        if key.startswith("USER_"):
            name = key[5:]
            phone = value.strip()
            if not phone.startswith("+"):
                continue
            existing = User.query.filter_by(phone=phone).first()
            if not existing:
                user = User(name=name, phone=phone, is_admin=(name in admin_names))
                db.session.add(user)
    db.session.commit()

# -------------------------------
# Chore Utilities
# -------------------------------
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

def complete_chore_by_name(chore_name, user):
    if not chore_name:
        return None
    chore = Chore.query.filter(
        Chore.assigned_to_id == user.id,
        Chore.name.ilike(f"%{chore_name.strip()}%"),
        Chore.completed == False
    ).first()
    if chore:
        chore.completed = True
        chore.completed_at = datetime.utcnow()
        db.session.commit()
        return chore
    return None

def list_user_chores(user, limit=5):
    chores = Chore.query.filter_by(assigned_to_id=user.id, completed=False)\
                .order_by(Chore.due_date.asc().nullslast())\
                .limit(limit).all()
    return [
        f"{c.name} (Due: {c.due_date.strftime('%Y-%m-%d') if c.due_date else 'No due date'})"
        for c in chores
    ]

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

# -------------------------------
# Conversation & Reminders
# -------------------------------
conversation_state = {}

def clean_conversations(app):
    """Remove stale conversation states after 2 hours."""
    with app.app_context():
        now = datetime.utcnow()
        expired = [k for k, v in conversation_state.items() if now - v['timestamp'] > timedelta(hours=2)]
        for k in expired:
            del conversation_state[k]

def send_reminders(app):
    """Send daily chore reminders."""
    with app.app_context():
        from chores_app import twilio_client
        from_number = os.getenv("TWILIO_NUMBER")
        today = datetime.now().date()

        for user in User.query.all():
            chores = Chore.query.filter(
                Chore.assigned_to_id == user.id,
                Chore.due_date != None,
                Chore.completed == False,
                Chore.due_date.date() == today
            ).all()
            if chores:
                message = f"Hey {user.name}, you have {len(chores)} chore(s) due today:\n"
                message += "\n".join(f"• {c.name}" for c in chores)
                twilio_client.messages.create(body=message, from_=from_number, to=user.phone)

def update_conversation_state(phone, intent, entities, expected_fields=None):
    conversation_state[phone] = {
        "intent": intent,
        "entities": entities,
        "timestamp": datetime.utcnow(),
        "missing": expected_fields or [],
    }

def continue_conversation(phone, message):
    state = conversation_state.get(phone)
    if not state:
        return None, None, None

    entities = state['entities']
    missing = state['missing']
    intent = state['intent']

    # Simple slot filling
    if intent == "add":
        if "chore_name" not in entities and "chore" in message.lower():
            entities["chore_name"] = message.strip()
            missing = [f for f in missing if f != "chore_name"]
        elif "assignee" not in entities:
            possible_user = get_user_by_name(message)
            if possible_user:
                entities["assignee"] = possible_user.name
                missing = [f for f in missing if f != "assignee"]
        elif "due_date" not in entities:
            parsed = parse_natural_date(message)
            if parsed:
                entities["due_date"] = parsed
                missing = [f for f in missing if f != "due_date"]

    # Save updated state
    conversation_state[phone]["entities"] = entities
    conversation_state[phone]["missing"] = missing

    return intent, entities, missing



# -------------------------------
# SMS Parsing & NLP
# -------------------------------
def parse_natural_date(text):
    text = text.lower().strip()
    if text == "today":
        return datetime.today()
    elif text == "tomorrow":
        return datetime.today() + timedelta(days=1)
    if match := re.match(r'in (\d+) days?', text):
        return datetime.today() + timedelta(days=int(match.group(1)))
    try:
        return date_parser.parse(text, fuzzy=True, default=datetime.today())
    except (ValueError, TypeError):
        return None

def parse_sms(body):
    text = re.sub(r"\s+", " ", body.strip().lower())
    intent = None
    entities = {}

    if text.startswith("done") or text.startswith("complete"):
        intent = "complete"
        entities["chore_name"] = text.replace("done", "").replace("complete", "").strip()

    elif text.startswith("add"):
        intent = "add"
        match = re.search(r"add (.*?) to (\w+)(?: due (.*?))?(?: every (\w+))?$", text)
        if match:
            entities["chore_name"] = match.group(1).strip()
            entities["assignee"] = match.group(2).strip()
            due_raw = match.group(3)
            recurrence = match.group(4)
            if due_raw:
                try:
                    entities["due_date"] = date_parser.parse(due_raw, fuzzy=True)
                except:
                    entities["due_date"] = None
            if recurrence:
                entities["recurrence"] = recurrence.lower()

    elif text.startswith("list"):
        intent = "list"

    elif text.startswith("unassign"):
        intent = "unassign"
        entities["chore_name"] = text.replace("unassign", "").strip()

    elif text in ["help"]:
        intent = "help"

    elif text in ["hi", "hello", "hey"]:
        intent = "greeting"

    elif "done" in text:
        intent = "complete"
        entities["chore_name"] = text.split("done", 1)[1].strip()

    return intent, entities

def parse_recurrence(text):
    text = text.lower()
    if "daily" in text:
        return "daily"
    elif "weekly" in text:
        return "weekly"
    elif "monthly" in text:
        return "monthly"
    elif match := re.search(r"every (\d+)", text):
        return f"every {match.group(1)}"
    return None

# -------------------------------
# SMS Send Utility
# -------------------------------
def send_sms(to, body):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")
    if not all([account_sid, auth_token, from_number]):
        print("Missing Twilio configuration.")
        return
    try:
        client = Client(account_sid, auth_token)
        client.messages.create(body=body, from_=from_number, to=to)
        print(f"Sent SMS to {to}: {body}")
    except Exception as e:
        print(f"Failed to send SMS to {to}: {e}")