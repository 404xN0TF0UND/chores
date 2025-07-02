# context_utils.py
from datetime import datetime, timedelta
from collections import defaultdict


class ConversationContext:
    def __init__(self):
        # In-memory context store: phone -> context dict
        self.store = defaultdict(dict)
        self.timeout = timedelta(minutes=5)  # Context expires after 5 minutes

    def get(self, phone):
        context = self.store.get(phone)
        if context and datetime.utcnow() - context.get("timestamp", datetime.utcnow()) < self.timeout:
            return context
        return None

    def set(self, phone, intent, entities):
        self.store[phone] = {
            "intent": intent,
            "entities": entities,
            "timestamp": datetime.utcnow()
        }

    def clear(self, phone):
        if phone in self.store:
            del self.store[phone]

    
class ContextTracker:
    def __init__(self):
        self.last_intent = None
        self.last_chore = None
        self.last_assignee = None
        self.last_due_date = None
        self.last_updated = datetime.now()

    def update(self, intent: str, entities: dict):
        self.last_intent = intent
        self.last_updated = datetime.now()
        if "chore" in entities:
            self.last_chore = entities["chore"]
        if "assignee" in entities:
            self.last_assignee = entities["assignee"]
        if "due_date" in entities:
            self.last_due_date = entities["due_date"]

    def summarize(self):
        return {
            "intent": self.last_intent,
            "chore": self.last_chore,
            "assignee": self.last_assignee,
            "due": self.last_due_date
        }