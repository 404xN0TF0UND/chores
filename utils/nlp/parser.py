# utils/nlp/parser.py

import re
from datetime import datetime
from typing import List, Tuple
import dateparser
from models import User

# --- Natural Language Utilities ---

def parse_natural_date(text: str) -> datetime | None:
    if not text:
        return None
    dt = dateparser.parse(text, settings={'PREFER_DATES_FROM': 'future'})
    return dt if isinstance(dt, datetime) else None

# --- Intent Parser ---

def parse_multiple_intents(message: str, sender: User | None = None) -> List[Tuple[str, dict]]:
    message = message.strip().lower()
    intents = []

    if "add" in message or "assign" in message:
        chore = extract_chore(message)
        assignee = extract_assignee(message, sender)
        due = extract_due_date(message)
        intents.append(("add", {
            "chore": chore,
            "assignee": assignee,
            "due_date": due
        }))

    elif "done" in message or "complete" in message:
        chore = extract_after_keyword(message, "done") or extract_after_keyword(message, "complete")
        intents.append(("done", {"chore": chore}))

    elif "list" in message:
        intents.append(("list", {}))

    elif "claim" in message:
        chore = extract_after_keyword(message, "claim")
        intents.append(("claim", {"chore": chore}))

    elif "delete" in message or "remove" in message:
        chore = extract_after_keyword(message, "delete") or extract_after_keyword(message, "remove")
        intents.append(("delete", {"chore": chore}))

    elif "unassign" in message:
        chore = extract_after_keyword(message, "unassign")
        intents.append(("unassign", {"chore": chore}))

    elif "broadcast" in message:
        msg = extract_after_keyword(message, "broadcast")
        intents.append(("broadcast", {"message": msg}))

    elif any(greet in message for greet in ("hi", "hello", "dusty")):
        intents.append(("greetings", {}))

    else:
        intents.append(("unknown", {}))

    return intents

# --- Helpers ---

def extract_after_keyword(text: str, keyword: str) -> str | None:
    match = re.search(rf"{keyword}\s+(.+)", text)
    return match.group(1).strip() if match else None

def extract_chore(text: str) -> str | None:
    match = re.search(r"(?:add|assign)\s+(.+?)(?:\s+(to|for)\s+|$)", text)
    return match.group(1).strip() if match else None

def extract_assignee(text: str, sender: User | None) -> str | None:
    match = re.search(r"(?:to|for)\s+([a-z\s]+)", text)
    if not match:
        return None

    raw = match.group(1).strip()
    name_token = raw.split()[0]  # Only take the first token

    if name_token in ("me", "myself") and sender:
        return sender.name.lower()
    return name_token

def extract_due_date(text: str) -> datetime | None:
    match = re.search(r"due\s+(.*)", text)
    if match:
        return parse_natural_date(match.group(1).strip())
    return None
       