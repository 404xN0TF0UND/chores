import re
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import User, Chore, Conversation
from twilio.rest import Client
import os

# --------------------
# Twilio Configuration
# --------------------

client = Client(os.environ['TWILIO_ACCOUNT_SID'], os.environ['TWILIO_AUTH_TOKEN'])
TWILIO_PHONE_NUMBER = os.environ['TWILIO_PHONE_NUMBER']

def send_sms(to, body):
    """Send an SMS using Twilio."""
    message = client.messages.create(
        body=body,
        from_=TWILIO_PHONE_NUMBER,
        to=to
    )
    return message.sid

# --------------------
# Chore Utilities
# --------------------

def get_user_by_phone(session: Session, phone_number: str):
    return session.query(User).filter(User.phone_number == phone_number).first()

def get_user_by_name(session: Session, name: str):
    return session.query(User).filter(User.name.ilike(name)).first()

def get_admins(session: Session):
    return session.query(User).filter(User.is_admin == True).all()

def get_due_chores(session: Session, due_date: datetime.date):
    return session.query(Chore).filter(
        Chore.due_date == due_date,
        Chore.completed == False
    ).all()

def get_incomplete_chores(session: Session):
    return session.query(Chore).filter(Chore.completed == False).all()

def get_user_assigned_chores(session: Session, user_id: int):
    return session.query(Chore).filter(
        Chore.assigned_to_id == user_id,
        Chore.completed == False
    ).order_by(Chore.due_date).limit(5).all()

def complete_chore(session: Session, chore: Chore):
    chore.completed = True
    chore.completed_at = datetime.utcnow()
    session.commit()

    # Notify admins
    admins = get_admins(session)
    for admin in admins:
        send_sms(admin.phone_number, f"✅ {chore.name} was completed by {chore.assigned_to.name}")

# ----------------------------
# Natural Language & Intents
# ----------------------------

def parse_recurrence(text: str):
    text = text.lower()
    if "daily" in text:
        return "daily"
    elif "weekly" in text:
        return "weekly"
    elif match := re.search(r"every (\d+) (day|days)", text):
        return f"every {match.group(1)}"
    return None

def parse_command(text: str):
    text = text.lower()

    # ADD vacuum to Erica due 2025-06-10
    if match := re.search(r"add (.+?) to (.+?) due (\d{4}-\d{2}-\d{2})", text):
        name, assignee, due_date = match.groups()
        recurrence = parse_recurrence(text)
        return {
            "intent": "add_chore",
            "name": name.strip(),
            "assignee": assignee.strip(),
            "due_date": due_date,
            "recurrence": recurrence,
        }

    # DONE dishes
    elif match := re.search(r"done (.+)", text):
        return {
            "intent": "complete_chore",
            "name": match.group(1).strip()
        }

    elif "list" in text:
        return {"intent": "list_chores"}

    return {"intent": "unknown"}

# ----------------------------
# Scheduled Task Utilities
# ----------------------------

def send_reminders(session: Session):
    today = datetime.utcnow().date()
    chores = get_due_chores(session, today)

    for chore in chores:
        if chore.assigned_to:
            send_sms(
                chore.assigned_to.phone_number,
                f"⏰ Reminder: '{chore.name}' is due today!"
            )

def clean_conversations(session: Session):
    expiration = datetime.utcnow() - timedelta(hours=12)
    session.query(Conversation).filter(Conversation.last_updated < expiration).delete()
    session.commit()

# ----------------------------
# Dusty Bot Personality
# ----------------------------

def dusty_response(message):
    if "done" in message.lower():
        return "Well look at you go. Another one bites the dust. 🧹"
    elif "list" in message.lower():
        return "Here's your filth inventory. Let's clean it up, champ:"
    elif "add" in message.lower():
        return "Another task? You're relentless. I'll add it to the pile."
    return "Dusty didn't quite get that. Maybe try again?"