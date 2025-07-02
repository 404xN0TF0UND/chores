import re
from datetime import datetime
from typing import List, Tuple, Dict, Optional
import spacy
import dateparser
from rapidfuzz import fuzz, process
from utils.context.context_utils import ContextTracker

nlp = spacy.load("en_core_web_sm")

TONE_ALIASES = {
    "gentle": ["gentle", "nice", "kind"],
    "sarcastic": ["sarcastic", "snarky", "mean", "rude"],
    "default": ["default", "normal", "regular"],
}

INTENT_KEYWORDS = {
    "add": ["add", "create"],
    "done": ["done", "complete", "finished", "mark"],
    "list": ["list", "show", "view"],
    "claim": ["claim", "take", "mine"],
    "unassign": ["unassign", "remove me", "give up"],
    "delete": ["delete", "remove", "trash"],
    "broadcast": ["broadcast", "announce"],
    "greetings": ["hi", "hello", "yo", "hey"],
    "help": ["help", "commands"],
}

FOLLOW_UP_VERBS = {"do", "mark", "remind", "delete", "assign", "postpone", "reschedule"}
FOLLOW_UP_PRONOUNS = {"it", "this", "that", "them", "her", "him"}


def detect_follow_up(doc) -> bool:
    verb_like = any(token.lemma_ in FOLLOW_UP_VERBS for token in doc)
    pronoun_like = any(token.lower_ in FOLLOW_UP_PRONOUNS for token in doc)
    return verb_like and pronoun_like

def resolve_intent(doc) -> str:
    # Prioritize known intent keywords first
    for token in doc:
        for intent, keywords in INTENT_KEYWORDS.items():
            if token.lemma_.lower() in keywords:
                return intent

    # Fallback: detect verb + pronoun combos like "do it", "remind her"
    if detect_follow_up(doc):
        return "follow_up"

    # Check for tone-setting intent
    if any(word in doc.text.lower() for word in ["set tone", "change tone", "tone", "be nice", "be mean"]):
        for tone, keywords in TONE_ALIASES.items():
            if any(k in doc.text.lower() for k in keywords):
                return "set_tone"
    return "unknown"



def parse_natural_date(text: str) -> Optional[datetime]:
    return dateparser.parse(text, settings={"PREFER_DATES_FROM": "future"})


def extract_entities(doc, sender: str, aliases: dict) -> dict:
    # --- Tone ---
    for tone, synonyms in TONE_ALIASES.items():
        if any(word in text for word in synonyms):
            entities["tone"] = tone
            break
    
    
    
    entities = {
        "chores": [],
        "assignee": None,
        "due_date": None,
        "recurrence": None
    }

    text = doc.text.lower()

    # --- Chore detection ---
    date_words = {
        "tomorrow", "today", "yesterday",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "week", "month", "day"
    }
    chore_candidates = []
    for token in doc:
        word = token.text.lower()
        if word in date_words:
            continue
        if token.pos_ in {"NOUN", "PROPN"} and token.ent_type_ != "PERSON":
            chore_candidates.append(word)
        elif token.pos_ == "VERB" and word.endswith("ing"):
            chore_candidates.append(word)

    if chore_candidates:
        entities["chores"] = chore_candidates

    # --- Assignee ---
    for i, token in enumerate(doc):
        token_text = token.text.lower()
        if token_text == "me":
            entities["assignee"] = aliases.get("me", sender)
            break
        elif token.ent_type_ == "PERSON":
            best_match = process.extractOne(token_text, aliases.keys(), scorer=fuzz.ratio)
            if best_match and best_match[1] >= 80:
                entities["assignee"] = aliases[best_match[0]]
            else:
                entities["assignee"] = token_text
            break
        elif token.lemma_ == "assign" and i + 2 < len(doc):
            if doc[i + 1].text.lower() in FOLLOW_UP_PRONOUNS:
                assignee_token = doc[i + 3] if doc[i + 2].text.lower() == "to" else doc[i + 2]
                best_match = process.extractOne(assignee_token.text.lower(), aliases.keys(), scorer=fuzz.ratio)
                if best_match and best_match[1] >= 80:
                    entities["assignee"] = aliases[best_match[0]]

    if not entities["assignee"]:
        entities["assignee"] = aliases.get("me", sender)

    # --- Recurrence ---
    recurrence_patterns = [
        (r"every day", "daily"),
        (r"every weekday", "weekdays"),
        (r"every weekend", "weekends"),
        (r"every week", "weekly"),
        (r"every other week", "biweekly"),
        (r"every month", "monthly"),
        (r"on the \d+(st|nd|rd|th) of each month", "monthly (specific day)")
    ]
    for pattern, label in recurrence_patterns:
        if re.search(pattern, text):
            entities["recurrence"] = label
            break

    if not entities["recurrence"]:
        matches = re.findall(
            r"(?:every|on|and)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            text
        )
        weekdays = list(dict.fromkeys([m.capitalize() for m in matches if m]))
        if weekdays:
            entities["recurrence"] = f"weekly ({', '.join(weekdays)})"

    # --- Due date ---
    due_match = re.search(r"due\s+(.*)", text)
    if due_match:
        parsed_date = parse_natural_date(due_match.group(1).strip())
        if parsed_date:
            entities["due_date"] = parsed_date

    return {k: v for k, v in entities.items() if v}

    
def parse_multiple_intents(message: str, sender: str = "", aliases: Dict[str, str] = {}, context: Optional[ContextTracker] = None) -> List[Tuple[str, Dict[str, any]]]:
    doc = nlp(message)

    # Early follow-up shortcut
    entities = extract_entities(doc, sender, aliases)
    if detect_follow_up(doc) and len(message.split(" then ")) == 1:
        if context:
            inferred = {
                "chore": context.last_chore,
                "assignee": context.last_assignee,
                "due_date": context.last_due_date,
            }
            return [("follow_up", {k: v for k, v in inferred.items() if v})]
        else:
            return [("follow_up", {"text": message.strip()})]

    # Segment message
    segments = []
    if " then " in message.lower():
        segments = [seg.strip() for seg in message.split(" then ")]
    else:
        temp_segment = []
        i = 0
        while i < len(doc):
            token = doc[i]
            if token.text.lower() == "and" and i + 1 < len(doc):
                next_tokens = [doc[j].text.lower() for j in range(i + 1, min(i + 4, len(doc)))]
                has_intent_after = any(
                    word in [kw for kwlist in INTENT_KEYWORDS.values() for kw in kwlist]
                    for word in next_tokens
                )
                if has_intent_after and temp_segment:
                    segments.append(" ".join([t.text for t in temp_segment]))
                    temp_segment = []
                else:
                    temp_segment.append(token)
            else:
                temp_segment.append(token)
            i += 1
        if temp_segment:
            segments.append(" ".join([t.text for t in temp_segment]))

    if not segments:
        segments = [message]

    intents = []
    for seg in segments:
        seg_doc = nlp(seg.strip())
        
        intent = resolve_intent(seg_doc)
        # Only fallback to follow up if no known intent was found
        if intent == "unknown" and detect_follow_up(seg_doc):
            intents.append(("follow_up" , {"text": seg.strip()}))
            continue
        entities = extract_entities(seg_doc, sender, aliases)

        if intent == "add":
            chores = entities.get("chores", [])
            for chore in chores:
                payload = {
                    "chore": chore,
                    "assignee": entities.get("assignee"),
                    "due_date": entities.get("due_date"),
                    "recurrence": entities.get("recurrence")
                }
                intents.append(("add", {k: v for k, v in payload.items() if v}))
        elif intent != "unknown":
            payload = {}
            if "chores" in entities and entities["chores"]:
                payload["chore"] = entities["chores"][0]
            if "assignee" in entities:
                payload["assignee"] = entities["assignee"]
            if "due_date" in entities:
                payload["due_date"] = entities["due_date"]
            if "recurrence" in entities:
                payload["recurrence"] = entities["recurrence"]
            intents.append((intent, payload))
        else:
            intents.append((intent, {"text": seg.strip()}))

    return intents