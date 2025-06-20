
# routes/sms.py

from flask import Blueprint, request
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime
import random

from models import db, Chore, ChoreHistory, ChoreStats, User
from utils.chores import get_unassigned_chores, list_user_chores
from utils.users import get_user_by_phone, get_user_by_name, reduce_fatigue
from utils.dusty import dusty_response, memory_based_commentary
from utils.nlp import parse_multiple_intents
from services.twilio_tools import send_sms
from utils.context import ContextTracker, ConversationContext
from utils.context.store import conversation_context

sms_bp = Blueprint("sms", __name__)
context_tracker = ConversationContext()
conversation_context = {}

def dusty_with_memory(key_or_text, **kwargs):
    user = kwargs.get("user")
    intent = key_or_text
    base = dusty_response(key_or_text, **kwargs)
    if isinstance(base, list):
        base = random.choice(base)
    extra = kwargs.get("extra")
    if extra and "{extra}" not in base and extra not in base:
        base = f"{base}\n{extra}"
    memory = memory_based_commentary(user, intent)
    if user:
        user.last_intent = intent
        user.last_seen = datetime.utcnow()
        if intent == "list":
            user.total_list_requests += 1
    return f"{base} {memory}".strip()


@sms_bp.route("/sms", methods=["POST"])
def handle_sms():
    print("[SMS ROUTE] Hit /sms endpoint")
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "").strip()
    print(f"[SMS RECEIVED] From: {from_number} | Message: '{incoming_msg}'")

    user = get_user_by_phone(from_number)
    if not user:
        return _twiml(dusty_with_memory("unauthorized"))

    context = conversation_context.get(user.name) or ContextTracker()

    # Fatigue management
    reduce_fatigue(user)
    if user.fatigue_level >= 10 and not any(x in incoming_msg.lower() for x in ["help", "greetings", "list"]):
        return _twiml(dusty_response(random.choice([
            "Nope. You're cut off. Dusty says: nap or perish.",
            "Fatigue Level: MAX. Task privileges revoked. Try again after eating a cookie.",
            "Dusty detected overachievement. Auto-throttling enabled.",
        ])))

    parsed_intents = parse_multiple_intents(incoming_msg)
    print(f"[MULTI-INTENT PARSE] {parsed_intents}")
    if not parsed_intents:
        return _twiml(dusty_response("unknown"))

    final_replies = []
    previous = context_tracker.get(from_number)

    # Fallback to prior context if needed
    intent, entities = parsed_intents[0]
    if intent in ("unknown", None) and previous:
        print("[CONTEXT] Resolving based on prior intent...")
        intent = previous["intent"]
        for k, v in previous["entities"].items():
            entities.setdefault(k, v)

    context_tracker.set(from_number, intent, entities)

    # Memory injection
    if context.last_intent and intent == "unknown":
        print("[CONTEXT FALLBACK] Using memory context.")
        for k in ["chore", "assignee", "due_date"]:
            if k not in entities and getattr(context, f"last_{k}"):
                entities[k] = getattr(context, f"last_{k}")

    for intent, entities in parsed_intents:
        user.last_intent = intent
        user.last_seen = datetime.utcnow()

        # Fatigue updates
        if intent in ["add", "list", "claim", "unassign", "delete"]:
            user.fatigue_level = min((user.fatigue_level or 0) + 1, 10)
        elif intent == "done":
            user.fatigue_level = max((user.fatigue_level or 0) - 2, 0)

        if intent == "add":
            reply = _handle_add(user, entities)
        elif intent == "done":
            reply = _handle_done(user, entities)
        elif intent == "list":
            reply = _handle_list(user)
        elif intent == "claim":
            reply = _handle_claim(user, entities)
        elif intent == "delete":
            reply = _handle_delete(user, entities)
        elif intent == "unassign":
            reply = _handle_unassign(user, entities)
        elif intent == "broadcast":
            reply = _handle_broadcast(user, entities)
        elif intent == "help":
            reply = dusty_with_memory("help", name=user.name)
        elif intent == "greetings":
            reply = dusty_with_memory("greetings", name=user.name)
        else:
            reply = dusty_with_memory("unknown", name=user.name)

        context.update(intent, entities)
        final_replies.append(reply)

    conversation_context[user.name] = context
    db.session.commit()
    return _twiml("\n\n".join(final_replies))


def _twiml(text):
    print(f"[Dusty Replying] {text}")
    resp = MessagingResponse()
    resp.message(text)
    return str(resp)


# -- Helper Intent Handlers --

def _handle_add(user, entities):
    name = entities.get("chore")
    assignee = get_user_by_name(entities.get("assignee")) if entities.get("assignee") else user
    due = entities.get("due_date")
    recurrence = entities.get("recurrence")
    if not name or not assignee:
        return dusty_with_memory("add_invalid", user=user)
    new_chore = Chore(name=name, assigned_to=assignee, due_date=due, recurrence=recurrence)
    db.session.add(new_chore)
    db.session.commit()
    extra = f"{name} assigned to {assignee.name}. Delegation level: expert." if assignee != user else f"{name} assigned to yourself. Brave soul."
    return dusty_with_memory("add", extra=extra, user=user)


def _handle_done(user, entities):
    name = entities.get("chore")
    if not name:
        last_chore = context_tracker.get_last_chore(user.id)
        if last_chore:
            entities["chore"] = last_chore.name
            name = last_chore.name
        else:
            context_tracker.set_last_intent(user.id, "mark_done_waiting_for_chore")
            return dusty_with_memory("done_invalid", user=user)
    chore = Chore.query.filter(
        Chore.name.ilike(f"%{name}%"),
        Chore.assigned_to_id == user.id,
        Chore.completed == False
    ).first()
    if not chore:
        return dusty_with_memory("not_found", extra=name, name=user.name)
    chore.completed = True
    chore.completed_at = datetime.utcnow()
    db.session.add(chore)
    stat = ChoreStats.query.filter_by(user_id=user.id, chore_name=chore.name).first()
    if stat:
        stat.times_completed += 1
    else:
        stat = ChoreStats(user_id=user.id, chore_name=chore.name, times_completed=1)
    db.session.add(stat)
    db.session.add(ChoreHistory(chore_name=chore.name, user_id=user.id, completed=True))
    user.total_chores_completed += 1
    fav = ChoreStats.query.filter_by(user_id=user.id).order_by(ChoreStats.times_completed.desc()).first()
    if fav:
        user.favorite_chore = fav.chore_name
    db.session.commit()
    return dusty_with_memory("done", extra=f"{chore.name} is finally off the list. Miracles happen.", user=user)


def _handle_list(user):
    chores = list_user_chores(user)
    if chores:
        lines = [f"- {c.name} (due {c.due_date.strftime('%Y-%m-%d') if c.due_date else 'anytime'})" for c in chores]
        return dusty_with_memory("list", extra="\n".join(lines), user=user)
    unassigned = get_unassigned_chores(limit=5)
    if unassigned:
        suggestion = "\nYou can claim one of these:\n" + "\n".join(
            f"- {c.name} (due {c.due_date.strftime('%Y-%m-%d') if c.due_date else 'anytime'})" for c in unassigned)
        return dusty_with_memory("no_chores", extra=suggestion, user=user)
    return dusty_with_memory("no_chores", user=user)


def _handle_claim(user, entities):
    name = entities.get("chore", "").strip().lower()
    chore = Chore.query.filter(Chore.name.ilike(f"%{name}%"), Chore.assigned_to_id == None).first()
    if chore:
        chore.assigned_to_id = user.id
        db.session.commit()
        return dusty_with_memory("claim", chore=chore.name, name=user.name)
    return dusty_with_memory("claim_fail", chore=name, name=user.name)


def _handle_delete(user, entities):
    name = entities.get("chore")
    if not name:
        return dusty_with_memory("delete_invalid", name=user.name)
    chore = Chore.query.filter(Chore.name.ilike(f"%{name}%")).first()
    if not chore or (not user.is_admin and chore.assigned_to_id != user.id):
        return dusty_with_memory("unauthorized", name=user.name)
    db.session.delete(chore)
    db.session.commit()
    return dusty_with_memory("deleted", extra=chore.name, name=user.name)


def _handle_unassign(user, entities):
    name = entities.get("chore")
    if not name:
        return dusty_with_memory("unassign_invalid", name=user.name)
    chore = Chore.query.filter(Chore.name.ilike(f"%{name}%"), Chore.completed == False).first()
    if not chore or (not user.is_admin and chore.assigned_to_id != user.id):
        return dusty_with_memory("unauthorized", name=user.name)
    chore.assigned_to_id = None
    db.session.commit()
    return dusty_with_memory("unassigned", extra=chore.name, name=user.name)


def _handle_broadcast(user, entities):
    if not user.is_admin:
        return dusty_with_memory("unauthorized", user=user)
    msg = entities.get("message")
    if not msg:
        return dusty_with_memory("broadcast_invalid", user=user)
    users = User.query.all()
    for u in users:
        if u.phone and u.phone != user.phone and u.phone.startswith("+1"):
            try:
                send_sms(u.phone, f"[Dusty 📣] {msg}")
            except Exception as e:
                print(f"[SMS ERROR] Failed to message {u.name} at {u.phone}: {e}")
    return dusty_with_memory("broadcast_success", extra="Your message is now everyone’s problem.", user=user)