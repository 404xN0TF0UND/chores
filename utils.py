
import os
import re
import random
import dateparser
from datetime import datetime, timedelta, date
from dateutil.parser import parser as parse_date, ParserError
from dateutil import parser as date_parser
from typing import Tuple
from models import Chore, User, ChoreHistory, db
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from twilio.rest import Client
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# -------------------------------
# Dusty Bot Personality & Messages
# -------------------------------

DUSTY_RESPONSES = {
    "greetings": [
        "Ah, greetings {name}. I trust you've been diligently avoiding your duties.",
        "Oh look, {name} decided to grace me with their presence.",
        "Hey {name}. What do you want *this* time?",
    ],
    "add": [
        "Another one? You sure know how to live on the edge of responsibility.",
        "Another task? You’re relentless. I’ll add it to the pile.",
        "Fine. I’ll write it down. Just don’t expect me to do it.",
        "Oh joy, more work. I’m thrilled.",
        "You humans sure love making messes for each other.",
        "Added. One more brick in the wall of responsibility.",
        "You keep assigning chores like it's a hobby.",
        "Fine. I’ll add it. But I won’t be happy about it.",
        "Chore added. Because obviously no one else was going to do it.",
    ],
    "done": [
        "Well look at you go. Another one bites the dust. 🧹",
        "You did a thing! Gold star for you. ⭐",
        "If I had hands, I'd slow clap. Nice work.",
        "Done already? Show-off.",
        "Another one off the list. You're making the rest of us look bad.",
        "You’ve earned a break. Don’t get used to it.",
        "It’s about time. I was starting to lose hope.",
        "Congrats. You’re 1% less useless now.",
    ],
    "list": [
        "Here’s your filth inventory. Let’s clean it up, champ:",
        "Ah, the glamorous life of domestic servitude. Behold your task list:",
        "The grime waits for no one. Here’s what’s left:",
        "These chores won’t clean themselves. Sadly, neither will you.",
        "Here’s what you still haven’t done. Just saying.",
        "Dusty's list of disappointment:",
        "You asked, I delivered. These chores won’t do themselves.",
        "Brace yourself. Chores ahead:",
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
        "Nope. Dusty’s circuits didn’t compute that nonsense.",
        "Whatever that was, it wasn’t a chore command.",
        "Your message was like a mystery novel — and Dusty doesn’t do fiction.",
        "I couldn't quite make sense of that. Try 'add dishes to Becky due Friday' or just cry quietly.",
        "Dusty does not compute. Try again with actual instructions.",
        "That's not a valid chore request, unless you meant to confuse me. In which case, congrats.",
    ],
}

DUSTY_SNARK = [
    "Wow, you're actually doing a chore? I'm shocked.",
    "Another one bites the dust. Literally.",
    "Impressive. You’ve done something for once.",
    "If chores were trophies, you'd almost deserve one.",
    "Keep this up and I’ll consider updating your résumé.",
    "I’m not saying you’re lazy, but your chores have their own zip code.",
    "Congratulations! You’ve achieved the bare minimum.",
    "I’d help, but I’m busy judging your life choices.",
    "You must be a magician, because you just made your chores disappear!",
    "You know, if you spent as much time cleaning as you do texting me, we’d be done by now.",
    "You call that cleaning? I’ve seen better results from a tornado.",
    "If I had a nickel for every chore you’ve done, I’d still be broke.",
    "I’m not saying you’re bad at chores, but I’ve seen better from toddlers.",
    "If procrastination were an Olympic sport, you’d win gold.",
    "You’re like a tornado of laziness. You leave chaos in your wake.",
]

HOLIDAY_SNARK = {
    "01-01": "New year, same dirty house. Chop chop!",
    "07-04": "Time to declare independence from laziness.",
    "12-25": "Even Santa makes his elves clean up.",
}

# -------------------------------
# Dusty Bot Logic & Utilities
# -------------------------------

def seasonal_greeting() -> str | None:
    """Return a holiday snark message if today is a recognized holiday."""
    today = datetime.utcnow()
    md = today.strftime("%m-%d")
    return HOLIDAY_SNARK.get(md)

def dusty_response(template_key_or_text, name=None, extra=None, include_seasonal=True) -> str:
    """
    Get a Dusty-style witty response from a category or literal string.
    Adds seasonal greeting and occasional snark.
    """
    if template_key_or_text in DUSTY_RESPONSES:
        message = random.choice(DUSTY_RESPONSES[template_key_or_text])
        message = message.format(name=name or "human", extra=extra or "")
    else:
        message = template_key_or_text  # treat as plain text fallback

    # 15% chance to add a roast
    if random.random() < 0.15 and DUSTY_SNARK:
        message += " " + random.choice(DUSTY_SNARK)

    # Add seasonal greeting if requested
    if include_seasonal:
        seasonal = seasonal_greeting()
        if seasonal:
            message += f" {seasonal}"

    return f"[Dusty 🤖] {message}"

def get_due_chores_message(session) -> str:
    """
    Retrieve all chores due today or overdue, format Dusty-style report.
    """
    today = datetime.utcnow().date()
    chores = (
        session.query(Chore)
        .options(joinedload(Chore.assigned_to))
        .filter(Chore.completed == False, Chore.due_date <= today)
        .all()
    )

    if not chores:
        return "[Dusty 🤖] Shockingly, there are no chores due today. Either you're efficient or lying."

    lines = ["[Dusty 🤖] Daily shame report:"]
    for chore in chores:
        name = chore.assigned_to.name if chore.assigned_to else "Unknown"
        due_str = chore.due_date.strftime("%Y-%m-%d") if chore.due_date else "No due date"
        lines.append(f"- {chore.description} (assigned to {name}, due {due_str})")

    return "\n".join(lines)

# -------------------------------
# User Seeding from Environment Variables
# -------------------------------

def seed_users_from_env(session):
    from sqlalchemy.exc import IntegrityError

    print("🔧 Seeding users from environment variables...")
    users_added = 0
    for key, value in os.environ.items():
        if key.startswith("USER_"):
            name = key.replace("USER_", "").strip()
            phone = value.strip()

            existing = session.query(User).filter_by(phone=phone).first()
            if existing:
                print(f"⚠️  Skipping existing user: {name} ({phone})")
                continue

            is_admin = name.lower() in ["ronnie", "becky"]  # ← mark admins
            user = User(name=name, phone=phone, is_admin=is_admin)
            session.add(user)
            users_added += 1

    try:
        session.commit()
        print(f"✅ Seeded {users_added} user(s).")
    except IntegrityError as e:
        session.rollback()
        print(f"❌ Integrity error during seeding: {e}")

# -------------------------------
# User Utilities
# -------------------------------

def get_user_by_phone(phone) :
    """Retrieve a user by their phone number."""
    
    return User.query.filter_by(phone=phone).first()

# -------------------------------
# SMS Parsing & NLP
# -------------------------------
# This function is used to parse the incoming SMS message and determine the intent.

def get_intent(message):
    message = message.strip().lower()
    intent_data = {"intent": None, "chore": None, "user": None, "due": None, "missing": []}

    # Match DONE
    match = re.match(r"done\s+(.*)", message)
    if match:
        intent_data["intent"] = "complete_chore"
        intent_data["chore"] = match.group(1).strip()
        return intent_data

    # Match LIST
    if message == "list":
        intent_data["intent"] = "list_chores"
        return intent_data

    # Match ADD (flexible)
    if message.startswith("add"):
        intent_data["intent"] = "add_chore"

        # Extract chore name
        chore_match = re.search(r"add\s+(.*?)(?:\s+to|\s+due|$)", message)
        if chore_match:
            intent_data["chore"] = chore_match.group(1).strip()

        # Extract user (to NAME)
        user_match = re.search(r"\bto\s+(\w+)", message)
        if user_match:
            intent_data["user"] = user_match.group(1).capitalize()

        # Extract due date (due YYYY-MM-DD or "tomorrow", etc.)
        due_match = re.search(r"\bdue\s+(\d{4}-\d{2}-\d{2}|\btomorrow\b|\btoday\b)", message)
        if due_match:
            due_text = due_match.group(1).strip()
            if due_text == "today":
                intent_data["due"] = datetime.today().date()
            elif due_text == "tomorrow":
                intent_data["due"] = datetime.today().date() + timedelta(days=1)
            else:
                try:
                    intent_data["due"] = datetime.strptime(due_text, "%Y-%m-%d").date()
                except ValueError:
                    pass

        # Track missing fields
        if not intent_data["chore"]:
            intent_data["missing"].append("chore")
        if not intent_data["user"]:
            intent_data["missing"].append("user")
        if not intent_data["due"]:
            intent_data["missing"].append("due")

        return intent_data

    return {"intent": "unknown", "message": message}

def parse_natural_date(text: str) -> datetime | None:
    if not text:
        return None

    text = text.strip().lower()
    today = datetime.today()

    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
    }

    if text in weekdays:
        target_day = weekdays[text]
        days_ahead = (target_day - today.weekday() + 7) % 7
        days_ahead = days_ahead or 7  # always move forward
        return today + timedelta(days=days_ahead)

    # Fallback: try natural language
    return dateparser.parse(text)

def parse_sms(text: str) -> tuple[str, dict]:
    text = text.strip().lower()
    print(f"[PARSE_SMS] Raw text: {text}")

    # Match: "add dishes to Becky due Friday every week"
    match = re.match(
        r"add\s+(?P<chore>.+?)(?:\s+to\s+(?P<user>\w+))?(?:\s+due\s+(?P<due>.*?))?(?:\s+every\s+(?P<recurrence>\w+))?$",
        text
    )

    if match:
        return "add", {
            "chore_name": match.group("chore").strip(),
            "assignee": match.group("user").strip() if match.group("user") else None,
            "due_date": match.group("due").strip() if match.group("due") else None,
            "recurrence": match.group("recurrence").strip() if match.group("recurrence") else None,
        }

    # Match: "done dishes"
    match = re.match(r"done\s+(?P<chore>.+)", text)
    if match:
        return "complete", { "chore_name": match.group("chore").strip() }

    # List
    if text in ("list", "ls"):
        return "list", {}

    # Help
    if text in ("help", "commands"):
        return "help", {}

    # Greetings
    if any(word in text for word in ["hi", "hello", "hey", "morning", "evening"]):
        return "greeting", {}

    return "unknown", {}
    
# -------------------------------
# Chore Utilities
# -------------------------------

def get_assigned_chores(user: User) -> list[Chore]:
    """Return list of incomplete chores assigned to user, ordered by due date."""
    return Chore.query.filter_by(assigned_to_id=user.id, completed=False).order_by(Chore.due_date).all()

def get_completed_chores(user: User) -> list[Chore]:
    """Return list of completed chores assigned to user, most recent first."""
    return Chore.query.filter_by(assigned_to_id=user.id, completed=True).order_by(Chore.completed_at.desc()).all()

def get_unassigned_chores():
    return Chore.query.filter_by(assigned_to_id=None).all()

def get_chore_history(user=None):
    query = ChoreHistory.query.order_by(ChoreHistory.completed_at.desc())
    if user:
        query = query.filter_by(completed_by_id=user.id)
    return query.all()

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

def notify_admins(message):
    
    admins = User.query.filter_by(is_admin=True).all()
    for admin in admins:
            twilio_client.messages.create(
            body=f"[Dusty Alert] {message}",
            from_= TWILIO_PHONE_NUMBER,
            to=admin.phone
        )
def get_upcoming_chores(user, days=3):
    now = datetime.now()
    upcoming = now + timedelta(days=days)
    return Chore.query.filter(
        Chore.assigned_to_id == user.id,
        Chore.due_date != None,
        Chore.completed == False,
        Chore.due_date <= upcoming
    ).order_by(Chore.due_date).all()


def list_user_chores(user, limit=5):
    chores = Chore.query.filter_by(assigned_to_id=user.id, completed=False)\
                .order_by(Chore.due_date.asc().nullslast())\
                .limit(limit).all()
    return [
        f"{c.name} (Due: {c.due_date.strftime('%Y-%m-%d') if c.due_date else 'No due date'})"
        for c in chores
    ]