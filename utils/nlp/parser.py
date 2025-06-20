# utils/nlp/parser.py

import re
from datetime import datetime
import dateparser
from typing import List, Tuple

from models import User  # make sure User is imported correctly

# -- Natural Date Parser --
def parse_natural_date(text: str) -> datetime | None:
    if not text:
        return None
    return dateparser.parse(text, settings={'PREFER_DATES_FROM': 'future'})

# -- Main Intent Parser --
def parse_multiple_intents(message: str, sender: User | None = None) -> List[Tuple[str, dict]]:
    message = message.strip().lower()
    intents = []

    if "add" in message or "assign" in message:
        chore = extract_chore_name(message)
        assignee = extract_assignee(message, sender)
        due = parse_natural_date(message)
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
    elif "help" in message:
        intents.append(("help", {}))
    elif "hi" in message or "hello" in message or "dusty" in message:
        intents.append(("greetings", {}))
    else:
        intents.append(("unknown", {}))

    return intents

# -- Entity Extraction Helpers --
def extract_after_keyword(text: str, keyword: str) -> str | None:
    match = re.search(rf"{keyword}\s+(.+)", text)
    return match.group(1).strip() if match else None

def extract_chore_name(text: str) -> str | None:
    # crude attempt to isolate chore from "add X to Y due Z"
    text = text.strip().lower()
    match = re.search(r"add\s+(.+?)\s+(to|for)\s+", text)
    if match:
        return match.group(1).strip()
    return extract_after_keyword(text, "add")

def extract_assignee(text: str, sender: User | None) -> str | None:
    # Check for "to <name>" or "for <name>"
    match = re.search(r"(to|for)\s+([a-z]+)", text)
    assignee = match.group(2).strip() if match else None
    if assignee in ("me", "myself") and sender:
        return sender.name.lower()
    return assignee