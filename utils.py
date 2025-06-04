import os
import random
import re
from dateutil import parser as date_parser
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from twilio.rest import Client

from models import User, Chore, Conversation

# --------------------
# Twilio Configuration
# --------------------
client = Client(os.environ['TWILIO_ACCOUNT_SID'], os.environ['TWILIO_AUTH_TOKEN'])
TWILIO_PHONE_NUMBER = os.environ['TWILIO_PHONE_NUMBER']


def send_sms(to: str, body: str) -> str:
    """Send an SMS using Twilio."""
    message = client.messages.create(
        body=body,
        from_=TWILIO_PHONE_NUMBER,
        to=to
    )
    return message.sid


# --------------------
# User & Chore Utilities
# --------------------

def get_user_by_phone(session: Session, phone_number: str) -> User | None:
    return session.query(User).filter(User.phone_number == phone_number).first()


def get_user_by_name(session: Session, name: str) -> User | None:
    return session.query(User).filter(User.name.ilike(name)).first()


def get_admins(session: Session) -> list[User]:
    return session.query(User).filter(User.is_admin.is_(True)).all()


def get_due_chores(session: Session, due_date: datetime.date) -> list[Chore]:
    return session.query(Chore).filter(
        Chore.due_date == due_date,
        Chore.completed.is_(False)
    ).all()


def get_incomplete_chores(session: Session) -> list[Chore]:
    return session.query(Chore).filter(Chore.completed.is_(False)).all()


def get_user_assigned_chores(session: Session, user_id: int) -> list[Chore]:
    return session.query(Chore).filter(
        Chore.assigned_to_id == user_id,
        Chore.completed.is_(False)
    ).order_by(Chore.due_date).limit(5).all()


def complete_chore(session: Session, chore: Chore):
    """Mark a chore complete and notify admins."""
    chore.completed = True
    chore.completed_at = datetime.utcnow()
    session.commit()

    admins = get_admins(session)
    for admin in admins:
        send_sms(
            admin.phone_number,
            f"✅ {chore.name} was completed by {chore.assigned_to.name}"
        )


# ----------------------------
# Natural Language & Intents
# ----------------------------

def parse_recurrence(text: str) :
    """Extract recurrence pattern from a message."""
    text = text.lower()
    if "daily" in text:
        return "daily"
    elif "weekly" in text:
        return "weekly"
    elif match := re.search(r"every (\d+) (day|days)", text):
        return f"every {match.group(1)}"
    return None


def parse_command(text: str):
     """Parse natural language SMS commands into structured intents."""
     text = text.strip().lower()
     response = {
        "intent": "unknown",
        "name": None,
        "assignee": None,
        "due_date": None,
        "recurrence": None,
    }

     # Check for "add chore" intent
     if any(kw in text for kw in ["add", "assign", "schedule"]):
        response["intent"] = "add_chore"

        # Extract chore name
        match = re.search(r"(?:add|assign|schedule)\s+(.*?)\s+(to|for)\s+", text)
        if match:
            response["name"] = match.group(1).strip()

        # Extract assignee
        match = re.search(r"(?:to|for)\s+(\w+)", text)
        if match:
            response["assignee"] = match.group(1).strip()

        # Extract due date
        date_match = re.search(r"(?:due|on)\s+(.*)", text)
        if date_match:
            try:
                parsed_date = date_parser.parse(date_match.group(1).strip(), fuzzy=True)
                response["due_date"] = parsed_date.strftime('%Y-%m-%d')
            except Exception:
                pass

        # Extract recurrence
        response["recurrence"] = parse_recurrence(text)

    # Check for "complete chore" intent
     elif any(kw in text for kw in ["done", "complete", "finished", "i did"]):
        response["intent"] = "complete_chore"
        match = re.search(r"(?:done|complete|finished|i did)\s+(.*)", text)
        if match:
            response["name"] = match.group(1).strip()

    # Check for "list chores" intent
     elif any(kw in text for kw in ["list", "show", "what", "chores", "tasks"]):
        response["intent"] = "list_chores"

     return response


# ----------------------------
# Scheduled Task Utilities
# ----------------------------

def send_reminders(session: Session):
    """Send SMS reminders for chores due today."""
    today = datetime.utcnow().date()
    chores = get_due_chores(session, today)

    for chore in chores:
        if chore.assigned_to:
            send_sms(
                chore.assigned_to.phone_number,
                f"⏰ Reminder: '{chore.name}' is due today!"
            )


def clean_conversations(session: Session):
    """Remove conversations inactive for 12+ hours."""
    expiration = datetime.utcnow() - timedelta(hours=12)
    session.query(Conversation).filter(
        Conversation.last_updated < expiration
    ).delete()
    session.commit()


# ----------------------------
# Dusty Bot Personality
# ----------------------------

DUSTY_RESPONSES = {
    "add": [
        "Another one? You sure know how to live on the edge of responsibility.",
        "Another task? You’re relentless. I’ll add it to the pile.",
        "Fine. I’ll write it down. Just don’t expect me to do it.",
        "Oh joy, more work. I’m thrilled.",
        "You humans sure love making messes for each other.",
        "Added. One more brick in the wall of responsibility."
        "You keep assigning chores like it's a hobby.",
        "Fine. I’ll add it. But I won’t be happy about it.",
        "Chore added. Because obviously no one else was going to do it."
    ],
    "done": [
        "Well look at you go. Another one bites the dust. 🧹",
        "You did a thing! Gold star for you. ⭐",
        "Well look at you go. Another one bites the dust. 🧹",
        "If I had hands, I'd slow clap. Nice work.",
        "Done already? Show-off.",
        "Another one off the list. You're making the rest of us look bad.",
        "You’ve earned a break. Don’t get used to it."
        "It’s about time. I was starting to lose hope.",
        "Congrats. You’re 1% less useless now.",
    ],
    "list": [
        "Here’s your filth inventory. Let’s clean it up, champ:",
        "Ah, the glamorous life of domestic servitude. Behold your task list:",
        "Here’s your filth inventory. Let’s clean it up, champ:",
        "The grime waits for no one. Here’s what’s left:",
        "These chores won’t clean themselves. Sadly, neither will you.",
        "Here’s what you still haven’t done. Just saying.",
        "Dusty's list of disappointment:"
        "You asked, I delivered. These chores won’t do themselves.",
        "Brace yourself. Chores ahead:"
    ],
    "add_fail": [
        "Add what? To who? When? Use your words.",
        "If you're trying to add a chore, maybe try being clearer.",
        "That add command was about as helpful as a chocolate teapot.",
    ],
    "unrecognized_user": [
        "Hmm, you’re not on the list. Dusty only works for the chosen few.",
        "Access denied. You might want to get adopted by someone on the list.",
    ],
    "unknown": [
        "Dusty didn’t quite get that. Maybe try again?",
        "Dusty didn’t quite get that. Try again, but with words that make sense.",
        "Are you speaking chore-ese? Because I don’t speak that.",
        "If you’re trying to confuse me, it’s working.",
        "Unclear. Uninspired. Unexecuted. Try again.",
        "Nope. Dusty’s circuits didn’t compute that nonsense."
        "Whatever that was, it wasn’t a chore command.",
        "Your message was like a mystery novel — and Dusty doesn’t do fiction.",
    ],
}

def get_random_roast(requesting_user=None):
    """Get a random roast for the user."""
    from models import db
    roasts = [
        "You call that cleaning? I’ve seen dust bunnies with more ambition.",
        "If procrastination were an Olympic sport, you’d win gold.",
        "You’re about as useful as a screen door on a submarine.",
        "I’ve seen sloths move faster than you do chores.",
        "You’re not lazy, you’re just on energy-saving mode.",
        "If you put as much effort into chores as you do into avoiding them, we’d be done by now.",
        "You’re like a tornado of laziness. You leave chaos in your wake.",
    ]
    with db.session() as session:
        cutoff = datetime.utcnow() - timedelta(days=7)
        eligible_users = session.query(User).filter(
            User.last_roasted_at == None or User.last_roasted_at < cutoff
        ).all()

        if not eligible_users:
            return "Dusty has no roasts left. You must be perfect."
        roast_target = random.choice(eligible_users)
        roast_target.last_roasted_at = datetime.utcnow()
        session.commit()

        if requesting_user and roast_target.name == requesting_user:
            return "Dusty can’t roast you, you’re already a masterpiece of procrastination."
        return f"{roast_target.name}, {random.choice(roasts)}"

def seasonal_greeting():
    today = datetime.utcnow()
    month ,day = today.month, today.day
    if month == 12 and day <= 26:
        return "Happy Holidays! Even dust deserves joy."
    elif month == 10 and day >= 25:
        return "Boo. Dusty’s here to haunt your chores."
    elif month == 7 and day == 4:
        return "Freedom isn’t free, and neither are clean dishes."
    elif month == 4 and day == 1:
        return "April Fools! But chores are no joke."
    elif month == 2 and day == 14:
        return "Roses are red, violets are blue, chores are waiting, and so are you."
        
    return None

def dusty_response(key="unknown"):
    responses = DUSTY_RESPONSES.get(key, DUSTY_RESPONSES["unknown"])
    response = random.choice(responses)

    # Seasonal greeting
    greeting = seasonal_greeting()
    if greeting:
        response += f" {greeting}"

    # Random roast (15% chance)
    if random.random() < 0.15:
        user = random.choice(["Erica", "Ronnie", "Becky"])
        response += f" (Also, {user}, you better not be slacking.)"

    return response