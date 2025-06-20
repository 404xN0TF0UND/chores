
# utils/nlp/parser.py

import re
from datetime import datetime
import dateparser
from typing import List, Tuple


def parse_natural_date(text: str) -> datetime | None:
    if not text:
        return None
    dt = dateparser.parse(text, settings={"PREFER_DATES_FROM": "future"})
    return dt if isinstance(dt, datetime) else None


def parse_multiple_intents(message: str) -> List[Tuple[str, dict]]:
    message = message.strip().lower()
    intents = []

    # Support multiple 'add' chunks like: "add laundry to Becky due Friday and dishes to me due Monday"
    if any(keyword in message for keyword in ["add", "assign", "give"]):
        chunks = re.split(r"\band\b", message)  # split multiple commands
        for chunk in chunks:
            if any(cmd in chunk for cmd in ["add", "assign", "give"]):
                intent = "add"
                assignee = extract_after_keyword(chunk, "to") or extract_after_keyword(chunk, "for")
                due = extract_due_date(chunk)
                chore = extract_chore_name(chunk, assignee)
                intents.append(
                    ("add", {
                        "chore": chore.strip() if chore else None,
                        "assignee": assignee.strip() if assignee else None,
                        "due_date": due
                    })
                )

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

    elif any(greet in message for greet in ["hi", "hello", "dusty"]):
        intents.append(("greetings", {}))

    else:
        intents.append(("unknown", {}))

    return intents


# Extract the chore description
def extract_chore_name(text: str, assignee: str | None) -> str:
    original = text
    text = re.sub(r"\b(add|assign|give|to|for|due|on|by)\b", "", text)
    if assignee:
        text = text.replace(assignee, "")
    return text.strip() if text.strip() else original.strip()


def extract_after_keyword(text: str, keyword: str) -> str | None:
    match = re.search(rf"{keyword}\s+([a-zA-Z0-9\s]+)", text)
    return match.group(1).strip() if match else None


def extract_due_date(text: str) -> datetime | None:
    # Try parsing after "due", "on", or "by"
    for keyword in ["due", "on", "by"]:
        match = re.search(rf"{keyword}\s+([a-zA-Z0-9,\s]+)", text)
        if match:
            parsed = parse_natural_date(match.group(1))
            if parsed:
                return parsed
    return None