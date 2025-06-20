import yaml
import os
import random
from datetime import datetime
from models import  User, db


# Path assumes dusty.py is in the same dir as dusty_responses.yaml
RESPONSES_PATH = os.path.join(os.path.dirname(__file__), "data", "dusty_responses.yaml")

with open(RESPONSES_PATH, "r") as f:
    dusty_config = yaml.safe_load(f)

DUSTY_RESPONSES = dusty_config["DUSTY_RESPONSES"]
DUSTY_SNARK = dusty_config["DUSTY_SNARK"]
HOLIDAY_SNARK = dusty_config["HOLIDAY_SNARK"]


# -------------------------------
# Dusty Bot Logic & Utilities
# -------------------------------

def seasonal_greeting() -> str | None:
    """Return a holiday snark message if today is a recognized holiday."""
    today = datetime.utcnow()
    md = today.strftime("%m-%d")
    return HOLIDAY_SNARK.get(md)

def dusty_response(template_key_or_text, include_seasonal=True, **kwargs) -> str:
    """Generate a Dusty-style response from a category key or literal string, with memory-aware sarcasm."""
    print(f"[DEBUG] Dusty called with: {template_key_or_text}")

    if template_key_or_text in DUSTY_RESPONSES:
        print("[DEBUG] Using category response")
        message = random.choice(DUSTY_RESPONSES[template_key_or_text])
        print(f"[DEBUG] Selected Dusty template: {message}")
    else:
        message = template_key_or_text

    # Safe formatting vars
    safe_kwargs = {
        "name": kwargs.get("name", "there"),
        "chore": kwargs.get("chore", "something unpleasant"),
        "due": kwargs.get("due", "someday"),
        **kwargs,
    }

    try:
        formatted = message.format(**safe_kwargs)
    except KeyError as e:
        print(f"[WARNING] Missing format key in Dusty response: {e}")
        formatted = message  # fallback

    # --- Memory-based sass injection ---
    user = kwargs.get("user")
    if user:
        # Sarcasm from fatigue
        if getattr(user, "fatigue_level", 0) > 5:
            formatted += " You alright? You look one chore away from collapse."

        # Roast chore obsession
        if getattr(user, "favorite_chore", None) and getattr(user, "total_chores_completed", 0) > 10:
            formatted += f" Also, what's with your {user.favorite_chore} obsession?"

        # Random roast, max once every 12h
        if random.random() < 0.15 and (
            not user.last_roast or (datetime.utcnow() - user.last_roast).total_seconds() > 43200
        ):
            burn = random.choice([
                "Even a Roomba has more initiative.",
                "You again? Starting to think you live here.",
                "If procrastination were a sport, you'd be on the podium.",
            ])
            formatted += f"\n🔥 {burn}"
            user.last_roast = datetime.utcnow()
            db.session.commit()

        # Timing-based wit
        if user.last_seen:
            minutes_ago = (datetime.utcnow() - user.last_seen).total_seconds() / 60
            if minutes_ago < 5 and random.random() < 0.5:
                formatted += f" (Back already? We just talked {int(minutes_ago)} minutes ago.)"
            if user.last_intent == template_key_or_text and random.random() < 0.5:
                formatted += " Déjà vu much?"

    # Seasonal greetings
    if include_seasonal:
        holiday = seasonal_greeting()
        if holiday and random.random() < 0.5:
            formatted += f" 🎉 {holiday}"

    # Random snark
    if random.random() < 0.15:
        formatted += f" 💥{random.choice(DUSTY_SNARK)}"


    # Fatigue sass (20% chance)
    if "user" in kwargs and isinstance(kwargs["user"], User):
        user = kwargs["user"]
    
    if user.fatigue_level and user.fatigue_level >= 7 and random.random() < 0.2:
        formatted += f" (Dusty’s noticing a fatigue level of {user.fatigue_level}/10. Pace yourself, overachiever.)"

    return f"[Dusty 🤖] {formatted}"

def memory_based_commentary(user, intent):
    if not user:
        return ""

    now = datetime.utcnow()
    minutes_ago = (now - user.last_seen).total_seconds() / 60 if user.last_seen else None

    comments = []

    # Roast if only adding chores
    if intent == "add" and user.total_chores_assigned > 10 and random.random() < 0.3:
        comments.append("Assigning chores again? Someone’s clearly discovered the joy of management.")
    
    # Repeat intent
    if user.last_intent == intent and random.random() < 0.4:
        comments.append("Déjà vu much?")

    # Quick return
    if minutes_ago is not None and minutes_ago < 3 and random.random() < 0.4:
        comments.append(f"(Back already? We just talked {int(minutes_ago)} minutes ago.)")

    # List spamming
    if intent == "list" and user.last_unassigned_seen >= 5  and random.random() < 0.3:
        comments.append("Five or more unassigned chores? is everyone on strike?")

        # Fatigue-based snark
    if user.fatigue_level >= 8 and random.random() < 0.5:
        fatigue_comments = [
            "You're really out here trying to impress someone, huh?",
            "Slow down, this isn’t a productivity cult.",
            "Ever heard of rest? It's free.",
            "Dusty’s concerned. And Dusty doesn’t do emotions.",
        ]
        comment += " " + random.choice(fatigue_comments)
    elif user.fatigue_level == 0 and intent == "done" and random.random() < 0.3:
        comment += " Well look at you. One chore and already back to couch mode?"

    return comment.strip()