import re
from utils.nlp.parser import parse_natural_date

def resolve_follow_up(message: str, context, sender: str):
    text = message.lower().strip()
    entities = {}
    intent = None

    # Determine fallback chore/assignee/due
    chore = context.last_chore
    assignee = context.last_assignee
    due_date = context.last_due_date

    # Basic intent inference
    if re.search(r"\b(done|do it|mark (it )?done)\b", text):
        intent = "done"
    elif "delete" in text or "remove" in text:
        intent = "delete"
    elif "assign" in text or "add" in text:
        intent = "add"
    elif "remind" in text or "postpone" in text or "move" in text:
        intent = "add"

    # Chore fallback
    
    if ("it" in text or "remind" in text or "postpone" in text) and chore:
        entities["chore"] = chore


    # Assignee detection
    match = re.search(r"(to|for)\s+(\w+)", text)
    if match:
        entities["assignee"] = match.group(2).lower()
    elif "her" in text and assignee:
        entities["assignee"] = assignee
    elif "me" in text:
        entities["assignee"] = sender

    # Due date
    match = re.search(r"(due|to|for)\s+(.*)", text)
    if match:
        parsed = parse_natural_date(match.group(2))
        if parsed:
            entities["due_date"] = parsed
    elif "tomorrow" in text:
        parsed = parse_natural_date("tomorrow")
        if parsed:
            entities["due_date"] = parsed

    return intent or "unknown", entities
