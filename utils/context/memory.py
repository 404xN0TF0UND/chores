# utils/context/memory.py

from datetime import datetime
import random

def memory_based_commentary(user, intent):
    """Generates a short memory-based sarcastic comment for Dusty."""
    if not user:
        return ""

    lines = []

    if user.total_list_requests >= 10 and intent == "list":
        lines.append("You're obsessed with lists. Minimalism isn’t for everyone.")

    if intent == "done" and user.favorite_chore:
        lines.append(f"Another {user.favorite_chore}? Someone has a type.")

    if user.fatigue_level >= 8:
        lines.append("Fatigue level critical. Send snacks.")

    return " ".join(lines)