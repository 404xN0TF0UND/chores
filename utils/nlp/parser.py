# utils/nlp/parser.py

import re
from datetime import datetime
import dateparser
from typing import List, Tuple

def parse_natural_date(text: str) -> datetime | None:
    if not text:
        return None
    dt = dateparser.parse(text, settings={'PREFER_DATES_FROM': 'future'})
    return dt if isinstance(dt, datetime) else None

def parse_multiple_intents(message: str) -> List[Tuple[str, dict]]:
    message = message.strip().lower()
    intents = []

    if "add" in message or "assign" in message:
        # Extract core parts
        chore = extract_between_keywords(message, "add", "to") or extract_after_keyword(message, "add")
        assignee = extract_after_keyword(message, "to")
        due = parse_natural_date(message)

        # Clean chore name (remove due phrases)
        if chore:
            chore = clean_chore_name(chore)

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

def extract_after_keyword(text: str, keyword: str) -> str | None:
    match = re.search(rf"{keyword}\s+(.+)", text)
    return match.group(1).strip() if match else None

def extract_between_keywords(text: str, start: str, end: str) -> str | None:
    match = re.search(rf"{start}\s+(.*?)\s+{end}", text)
    return match.group(1).strip() if match else None

def clean_chore_name(raw: str) -> str:
    raw = re.sub(r"\bdue\s+\w+", "", raw)            # "due today"
    raw = re.sub(r"\bdue\s+on\s+\w+", "", raw)       # "due on Friday"
    raw = re.sub(r"\bby\s+\w+", "", raw)              # "by Monday"
    return raw.strip()
 