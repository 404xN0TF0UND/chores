
import re
from datetime import datetime
from typing import List, Tuple, Optional
import dateparser

# ---- Helper Functions ----

def parse_natural_date(text: str) -> Optional[datetime]:
    """Convert natural date phrases like 'today' or 'next Friday' into a datetime."""
    if not text:
        return None
    dt = dateparser.parse(text, settings={'PREFER_DATES_FROM': 'future'})
    return dt if isinstance(dt, datetime) else None

def extract_after_keyword(text: str, keyword: str) -> Optional[str]:
    match = re.search(rf"{keyword}\s+(.+)", text)
    return match.group(1).strip() if match else None

def extract_between_keywords(text: str, start: str, end: str) -> Optional[str]:
    match = re.search(rf"{start}\s+(.*?)\s+{end}", text)
    return match.group(1).strip() if match else None

def resolve_alias(assignee: Optional[str], sender_name: str) -> str:
    if assignee in ["me", "myself", "i", None]:
        return sender_name.lower()
    return assignee.lower()

# ---- Main Parser ----

def parse_multiple_intents(message: str, sender_name: str = "") -> List[Tuple[str, dict]]:
    message = message.strip().lower()
    intents = []

    if "add" in message or "assign" in message:
        msg = message.replace("assign", "add")

        # Step 1: Extract due date string
        due_match = re.search(r"due\s+([a-zA-Z0-9\s]+)", msg)
        due_str = due_match.group(1).strip() if due_match else None
        due_date = parse_natural_date(due_str) if due_str else None
        if due_str:
            msg = re.sub(r"due\s+" + re.escape(due_str), "", msg)

        # Step 2: Extract assignee (to/for)
        assignee_match = re.search(r"(?:to|for)\s+(\w+)", msg)
        assignee = assignee_match.group(1).strip() if assignee_match else None
        if assignee:
            msg = re.sub(r"(?:to|for)\s+" + re.escape(assignee), "", msg)

        assignee = resolve_alias(assignee, sender_name)

        # Step 3: Extract chore (what’s left after “add”)
        chore = msg
        if chore.startswith("add "):
            chore = chore[4:]
        chore = chore.strip()

        intents.append(("add", {
            "chore": chore,
            "assignee": assignee,
            "due_date": due_date
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

    elif any(greet in message for greet in ["hi", "hello", "dusty"]):
        intents.append(("greetings", {}))

    else:
        intents.append(("unknown", {}))

    return intents   
     