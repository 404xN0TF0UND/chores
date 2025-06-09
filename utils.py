
import os
import re
import random
import dateparser
from datetime import datetime, timedelta, date
# from dateutil.parser import parse, ParserError
# from dateutil import parser as date_parser
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
        "Well, if it isn't {name}. Here to procrastinate or actually do something?",
        "Hello {name}. I hope you're ready to face the mountain of chores you've ignored.",
        "Greetings, {name}. Dusty is here to remind you that chores don’t do themselves.",
        "Well, well, if it isn’t {name}. Ready to tackle your responsibilities or just here to chat?",
        "Ah, {name}. The procrastinator returns. What’s on your mind?",
        "Hello {name}. I see you’ve come to face the music. Or at least, the dust.",
        "Hey {name}. I hope you’re ready to get your hands dirty. Literally.",
        "Well, if it isn’t {name}. Here to avoid chores or just looking for excuses?",
        "Greetings, {name}. Dusty is here to remind you that chores don’t do themselves.",
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
    "unassigned": [
        "You can’t claim a chore that doesn’t exist. Try again.",
        "No unassigned chores found. Dusty’s not a miracle worker.",
        "Claim what? There are no chores waiting for you.",
        "You can’t claim a chore that’s already taken. Try harder.",
        "No unclaimed chores available. Dusty’s not a charity.",
        "You’re trying to claim a chore that’s already claimed. Nice try.",
        "Claiming a chore that’s already assigned? Dusty doesn’t think so.",
        "You can’t claim a chore that’s already in progress. Try again later.",
        "No unclaimed chores available. Dusty’s not a miracle worker.",
        "You can’t claim a chore that’s already taken. Nice try.",
        "Claiming a chore that’s already assigned? Dusty doesn’t think so.",
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
    "claim": [
        "Claimed! You’re now responsible for this chore. Don’t mess it up.",
        "You’ve claimed it. Now don’t make me regret it.",
        "Chore claimed. You’re on the hook now, {name}.",
        "You’ve got it. Don’t think you can back out now.",
        "Claimed! You’re now the proud owner of this chore. Enjoy.",
        "Congratulations! You’ve just inherited a chore. Lucky you.",
        "You’ve claimed it. Now get to work before I change my mind.",
        "Chore claimed. You’re now the designated slacker.",
        "You’ve claimed it. Don’t let it go to waste, {name}.",
        "Chore claimed! You’re now the official procrastinator.",
    
    ],
    "help": [
        "Need help? Here’s what Dusty can do:\n"
        "• `add <chore> to <user> due <date>` - Assign a chore\n"
        "• `done <chore>` - Mark a chore as completed\n"
        "• `claim <chore>` - Claim an unassigned chore\n"
        "• `list` - Show your assigned chores\n"
        "• `help` - Show this message\n"
        "• `greeting` - Get a Dusty-style greeting\n"
        "Remember, Dusty is here to help... or roast you. Your choice.",
        "Dusty’s help desk is open! Here’s what you can do:\n"
        "• `add <chore> to <user> due <date>` - Assign a chore to someone\n"
        "• `done <chore>` - Mark a chore as done\n"
        "• `claim <chore>` - Claim an unassigned chore\n"
        "• `list` - List your assigned chores\n"
        "• `help` - Show this message\n"
        "• `greeting` - Get a Dusty-style greeting\n"
        "Use wisely, or Dusty might just roast you instead.",
    ],
    "done_invalid": [
        "Done what? You need to specify a chore to mark as done.",
        "Dusty can’t read your mind. Specify the chore you completed.",
        "You need to tell me which chore you just finished. Dusty’s not a mind reader.",
    ],
    "no_chore": [
        "You haven’t specified a chore to mark as done. Try again.",
        "Dusty can’t mark a chore as done without a name. Specify one.",
        "You need to tell me which chore you just finished. Dusty’s not a mind reader.",
        "Invalid done request. Specify the chore you want to mark as done.",
        "You can’t mark a chore as done without naming it. Try again.",
        "Dusty needs a chore name to process your request. Specify one.",
        "Dusty can’t read your mind. Specify the chore you completed.",
        "You need to tell me which chore you just finished. Dusty’s not a mind reader.",
    ],

    "claim_invalid": [
        "Claim what? You need to specify a chore to claim.",
        "Dusty can’t claim chores without a name. Specify one.",
        "You need to tell me which chore you want to claim. Dusty’s not a psychic.",
        "Invalid claim request. Specify the chore you want to claim.",
        "You can’t claim a chore without naming it. Try again.",
        "Dusty needs a chore name to process your claim. Specify one.",
        "Invalid claim command. You must specify a chore to claim.",
        "You can’t claim a chore without a name. Specify one.",
        "Dusty needs a chore name to process your claim. Specify one.",
    ],
    "claim_fail": [
        "No such chore to claim. Try again with a valid one.",
        "That chore is already claimed. Try another one.",
        "Claim failed. Either the chore doesn’t exist or it’s already taken.",
        "You can’t claim that chore. It’s already assigned to someone else.",
        "Claim failed. Either the chore is already taken or doesn’t exist.",
        "That chore is already claimed. Try claiming an unassigned one.",
        "Claim failed. Either the chore is already taken or doesn’t exist.",
        "You can’t claim that chore. It’s already assigned to someone else.",
    ],
    "claim_success": [
        "Claimed! You’re now responsible for this chore. Don’t mess it up.",
        "You’ve claimed it. Now don’t make me regret it.",
        "Chore claimed. You’re on the hook now, {name}.",
        "You’ve got it. Don’t think you can back out now.",
        "Claimed! You’re now the proud owner of this chore. Enjoy.",
        "Congratulations! You’ve just inherited a chore. Lucky you.",
        "You’ve claimed it. Now get to work before I change my mind.",
        "Chore claimed. You’re now the designated slacker.",
        "You’ve claimed it. Don’t let it go to waste, {name}.",
        "Chore claimed! You’re now the official procrastinator.",
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

def dusty_response(template_key_or_text, include_seasonal=True, **kwargs) -> str:
    """
    Generate a Dusty-style response from a category key or literal string.

    Args:
        template_key_or_text (str): Key in DUSTY_RESPONSES or raw response.
        include_seasonal (bool): Include seasonal message if available.
        **kwargs: Variables to inject (e.g., name, chore).
    """
    print(f"[DEBUG] Dusty called with: {template_key_or_text}")
    message = None

    if template_key_or_text in DUSTY_RESPONSES:
        print("[DEBUG] Using category response")
        message = random.choice(DUSTY_RESPONSES[template_key_or_text])
    else:
        message = template_key_or_text

    try:
        formatted = message.format(**kwargs)
    except KeyError as e:
        print(f"[WARNING] Missing format key in Dusty response: {e}")
        formatted = message  # fallback to raw if formatting fails

    # Add seasonal snark occasionally
    if include_seasonal:
        holiday = seasonal_greeting()
        if holiday and random.random() < 0.5:
            formatted += f" 🎉 {holiday}"

    # 15% chance to add snark
    if random.random() < 0.15:
        roast = random.choice(DUSTY_SNARK)
        formatted += f" 💥 {roast}"

    return f"[Dusty 🤖] {formatted}"

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
def get_user_by_name(name: str) -> User | None:
    """Retrieve a user by their name (case-insensitive)."""
    return User.query.filter(User.name.ilike(name.strip())).first()

def get_user_by_phone(phone) :
    """Retrieve a user by their phone number."""
    
    return User.query.filter_by(phone=phone).first()

# -------------------------------
# SMS Parsing & NLP
# -------------------------------
# This function is used to parse the incoming SMS message and determine the intent.

# def get_intent(message: str) -> Tuple[str, dict]:
#     """Determine user intent and extract entities from a natural SMS."""
#     message = message.lower().strip()
#     entities = {}

#     # Shortcut commands
#     if message in ["list", "my chores"]:
#         return "list", {}
#     if message in ["help", "commands"]:
#         return "help", {}
#     if message in ["hello", "hi", "hey", "greetings"]:
#         return "greeting", {}
    
#     # DONE intent
#     if message.startswith("done"):
#         match = re.match(r"done\s+(.*)", message)
#         if match:
#             entities["chore"] = match.group(1).strip()
#             return "done", entities

#     # CLAIM intent
#     if message.startswith("claim"):
#         match = re.match(r"claim\s+(.*)", message)
#         if match:
#             entities["chore"] = match.group(1).strip()
#             return "claim", entities

#     # ADD intent
#     add_match = re.match(r"(add|assign)\s+(.*?)\s+to\s+(\w+)\s+due\s+(.*)", message)
#     if add_match:
#         _, chore_name, assignee, due_str = add_match.groups()
#         entities["chore"] = chore_name.strip()
#         entities["assignee"] = assignee.strip()
#         due_date = dateparser.parse(due_str)
#         if due_date:
#             entities["due_date"] = due_date.date()
#         return "add", entities

#     return "unknown", {}

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



# def parse_sms(message):
#     print(f"[NLP DEBUG] Parsing: {message}")

#     message = message.lower().strip()

#     # Normalize some synonyms
#     message = message.replace("assign", "add").replace("for", "to").replace("on", "due")

#     if not message.startswith("add "):
#         print("[NLP DEBUG] Not an ADD command")
#         return None

#     # Token-based heuristics
#     parts = message[4:].split(" due ")

#     if len(parts) < 2:
#         print("[NLP DEBUG] Missing due date phrase")
#         return None

#     before_due, after_due = parts
#     chore_part = before_due.strip()  # e.g. 'vacuum to Becky'

#     if " to " not in chore_part:
#         print("[NLP DEBUG] Missing 'to' to identify assignee")
#         return None

#     chore_name, assignee_name = chore_part.split(" to ", 1)
#     chore_name = chore_name.strip()
#     assignee_name = assignee_name.strip()

#     # Handle recurrence if present
#     recurrence = None
#     if " every " in after_due:
#         due_text, recurrence_text = after_due.split(" every ", 1)
#         recurrence = recurrence_text.strip()
#     else:
#         due_text = after_due.strip()

#     # Parse due date naturally
#     try:
#         due_date = dateparser.parse(due_date_str)
#     except Exception as e:
#         print(f"[NLP DEBUG] Failed to parse due date: {e}")
#         return None

#     print(f"[NLP DEBUG] Extracted chore='{chore_name}', assignee='{assignee_name}', due='{due_date}', recurrence='{recurrence}'")
#     return chore_name, assignee_name, due_date, recurrence

def parse_sms_nlp(message: str) -> Tuple[str, dict]:
    """
    Parses the SMS message to determine intent and extract entities.
    Supports natural phrasing for add, done, list, claim, and help.
    Returns: (intent: str, entities: dict)
    """
    message_lower = message.strip().lower()
    entities = {}

    print(f"[NLP DEBUG] Parsing: {message}")

    # -------------------------------
    # 1. Help / Greeting / List
    # -------------------------------
    if any(word in message_lower for word in ['help', 'commands', 'what can you do']):
        return "help", {}

    if any(word in message_lower for word in ['hi', 'hello', 'greetings', 'hey', 'howdy', 'yo', 'sup']):
        return "greetings", {}

    if message_lower.startswith("list"):
        return "list", {}

    # -------------------------------
    # 2. Done Intent
    # -------------------------------
    if message_lower.startswith("done"):
        chore = message_lower.replace("done", "").strip()
        if chore:
            entities["chore"] = chore
            return "done", entities
        else:
            return "done_invalid", {}

    # -------------------------------
    # 3. Claim Intent
    # -------------------------------
    if message_lower.startswith("claim"):
        chore = message_lower.replace("claim", "").strip()
        if chore:
            entities["chore"] = chore
            return "claim", entities
        else:
            return "claim_invalid", {}

    # -------------------------------
    # 4. Add Intent
    # -------------------------------
    if message_lower.startswith("add"):
        # Example: "Add dishes to Becky due Friday"
        pattern = r"add (.+?) to ([\w\s]+?) due (.+)"
        match = re.match(pattern, message_lower)

        if match:
            chore = match.group(1).strip()
            assignee = match.group(2).strip()
            due_str = match.group(3).strip()

            entities["chore"] = chore
            entities["assignee"] = assignee

            try:
                parsed_date = dateparser.parse(due_str)
                if parsed_date:
                    entities["due_date"] = parsed_date.date()
                else:
                    print(f"[NLP DEBUG] Failed to parse due date: '{due_str}' → None")
                    return "add_invalid", {}
            except Exception as e:
                print(f"[NLP DEBUG] Exception during date parsing: {e}")
                return "add_invalid", {}

            return "add", entities
        else:
            print("[NLP DEBUG] Add intent pattern did not match.")
            return "add_invalid", {}

    # -------------------------------
    # 5. Fallback
    # -------------------------------
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
    print(f"[DEBUG] Inside list_user_chores: Found {chores}")
    return chores