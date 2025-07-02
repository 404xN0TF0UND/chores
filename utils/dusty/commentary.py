import random
from datetime import datetime, timedelta

def generate_commentary(context, user, intent, entities):
    comments = []

    chore = entities.get("chore")
    last_chore = context.last_chore
    last_intent = context.last_intent
    now = datetime.now()
    recently_updated = context.last_updated and (now - context.last_updated < timedelta(minutes=2))

    # ✨ Repeating same chore
    if chore and chore == last_chore and intent == "add":
        comments.append(f"{chore.title()} again? Dusty’s getting déjà vu... or you’re just predictable.")

    # 🥵 Fatigue sarcasm
    if intent == "add" and (user.fatigue_level or 0) >= 8:
        comments.append("More chores? Should I contact OSHA?")

    # 🙌 Praise for follow-through
    if intent == "done" and last_intent == "add" and chore == last_chore:
        comments.append(f"Whoa. You actually finished {chore}? Dusty is... stunned.")

    # ⏱️ Rapid-fire responses
    if recently_updated:
        comments.append("Back already? Someone’s needy.")

    # 🧼 Sudden cleaning spree
    if intent == "done" and (user.fatigue_level or 0) <= 2:
        comments.append("A chore? Done? You okay, champ? Blink twice if Dusty should worry.")

    # 🧠 Forgotten context roast
    if intent == "done" and not chore:
        comments.append("Mark *what* done? Dusty isn’t psychic. Yet.")

    # 🧩 Fallback general snark
    if not comments:
        comments.append(random.choice([
            "Dusty is processing... your nonsense.",
            "Let’s pretend that made sense and move on.",
            "You sure that’s how chores work?",
            "Dusty is adding that to your permanent record.",
        ]))

    return random.choice(comments)