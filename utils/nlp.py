# import re
# from typing import Tuple, List
# import dateparser
# from datetime import datetime, timedelta

# def parse_natural_date(text: str) -> datetime | None:
#     if not text:
#         return None
#     text = text.strip().lower()
#     today = datetime.today()
#     weekdays = {
#         "monday": 0, "tuesday": 1, "wednesday": 2,
#         "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
#     }
#     if text in weekdays:
#         target_day = weekdays[text]
#         days_ahead = (target_day - today.weekday() + 7) % 7
#         days_ahead = days_ahead or 7  # always move forward
#         return today + timedelta(days=days_ahead)

#     return dateparser.parse(text)

# def parse_sms_nlp(message: str) -> Tuple[str, dict]:
#     """ Parses the SMS message to determine intent and extract entities. """
#     message_lower = message.strip().lower()
#     entities = {}
#     print(f"[NLP DEBUG] Parsing: {message}")

#     # -------------------------------
#     # 1. Help / Greeting / List
#     # -------------------------------
#     if any(word in message_lower for word in ['help', 'commands', 'what can you do']):
#         return "help", {}
#     if any(word in message_lower for word in ['hi', 'hello', 'greetings', 'hey', 'howdy', 'yo', 'sup']):
#         return "greetings", {}
#     if "list" in message_lower or "show" in message_lower or "what do i have" in message_lower:
#         return "list", {}

#     # -------------------------------
#     # 2. Done Intent
#     # -------------------------------
#     done_keywords = ["done", "finished", "completed", "i did", "i’m done", "marked off", "checked off"]
#     if any(kw in message_lower for kw in done_keywords):
#         for kw in done_keywords:
#             if kw in message_lower:
#                 chore = message_lower.replace(kw, "").strip(" :.")
#                 if chore:
#                     entities["chore"] = chore
#                     return "done", entities
#                 else:
#                     return "done", {}
#         return "done", {}

#     # -------------------------------
#     # 3. Claim Intent
#     # -------------------------------
#     claim_keywords = ["claim", "i’ll take", "assign me", "i want", "give me"]
#     if any(kw in message_lower for kw in claim_keywords):
#         for kw in claim_keywords:
#             if kw in message_lower:
#                 chore = message_lower.replace(kw, "").strip(" :.")
#                 if chore:
#                     entities["chore"] = chore
#                     return "claim", entities
#                 else:
#                     return "claim", {}
#         return "claim", {}

#     # -------------------------------
#     # 4. Add / Assign Intent (Smarter NLP)
#     # -------------------------------
#     add_verbs = ["add", "assign", "remind", "schedule", "make", "tell", "have", "get"]

#     if any(message_lower.startswith(v) for v in add_verbs) or " to " in message_lower:
#         try:
#             # Try to extract chore, assignee, and due date
#             tokens = message_lower.split()
#             chore = None
#             assignee = None
#             due_date = None

#             if " to " in message_lower:
#                 chore_part, remainder = message_lower.split(" to ", 1)
#                 chore = chore_part
#             else:
#                 remainder = message_lower

#             if " due " in remainder:
#                 assignee_part, due_part = remainder.split(" due ", 1)
#                 assignee = assignee_part
#                 due_date = parse_natural_date(due_part.strip())
#             else:
#                 assignee = remainder
#                 due_date = None

#             if chore:
#                 for verb in add_verbs:
#                     if chore.startswith(verb):
#                         chore = chore[len(verb):].strip()
#                         break

#             if chore:
#                 entities["chore"] = chore.strip()
#             if assignee:
#                 entities["assignee"] = assignee.strip()
#             if due_date:
#                 entities["due_date"] = due_date.date()

#             if "chore" in entities and "assignee" in entities:
#                 return "add", entities
#             else:
#                 return "add_invalid", {}

#         except Exception as e:
#             print(f"[NLP DEBUG] Exception during add intent NLP: {e}")
#             return "add_invalid", {}

#     # -------------------------------
#     # 5. Broadcast (Admin Only)
#     # -------------------------------
#     if message_lower.startswith(("broadcast", "announce", "msg all")):
#         return "broadcast", { "message": message.partition(" ")[2].strip() }

#     # -------------------------------
#     # 6. Fallback
#     # -------------------------------
#     return "unknown", {}

# def split_message_into_chunks(message: str) -> List[str]:
#     """ Splits the message into chunks by 'and', 'then', or punctuation. """
#     separators = r"\b(?:and|then)\b|[.,;]"
#     parts = re.split(separators, message, flags=re.IGNORECASE)
#     return [part.strip() for part in parts if part.strip()]

# def parse_multiple_intents(message: str) -> List[Tuple[str, dict]]:
#     """ Parses a message that may contain multiple intents. """
#     chunks = split_message_into_chunks(message)
#     parsed = []
#     for chunk in chunks:
#         intent, entities = parse_sms_nlp(chunk)
#         if intent != "unknown":
#             parsed.append((intent, entities))
#     return parsed