# utils/nlp/parser.py

import re
from datetime import datetime, timedelta
import dateparser
from typing import List, Tuple

# Parse natural language date strings into datetime
def parse_natural_date(text: str) -> datetime | None:
    if not text:
        return None
    dt = dateparser.parse(text, settings={'PREFER_DATES_FROM': 'future'})
    return dt if isinstance(dt, datetime) else None

# Primary intent and entity parser
def parse_multiple_intents(message: str) -> List[Tuple[str, dict]]:
    message = message.strip().lower()
    intents = []

    if "add" in message or "assign" in message:
        # Example: "Add laundry for Erica tomorrow"
        chore = extract_between_keywords(message, "add", "for") or extract_after_keyword(message, "add")
        assignee = extract_after_keyword(message, "for")
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

# Helper functions
def extract_after_keyword(text: str, keyword: str) -> str | None:
    match = re.search(rf"{keyword}\s+(.+)", text)
    return match.group(1).strip() if match else None

def extract_between_keywords(text: str, start: str, end: str) -> str | None:
    match = re.search(rf"{start}\s+(.*?)\s+{end}", text)
    return match.group(1).strip() if match else None

        