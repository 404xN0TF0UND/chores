import os
from flask import Flask, request, render_template, redirect, url_for, flash
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime
from models import db, User, Chore, ChoreHistory
from sqlalchemy.orm import joinedload
from scheduler import start_scheduler
from utils import (
    seed_users_from_env, get_user_by_phone, get_user_by_name,
    dusty_response, get_assigned_chores, get_completed_chores,
    get_unassigned_chores, get_chore_history, complete_chore_by_name,
    notify_admins, get_upcoming_chores, list_user_chores,
    parse_natural_date,parse_sms_nlp
)
print("[BOOT] Flask is starting up")
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chores.db'
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "shhh")
db.init_app(app)

with app.app_context():
    db.create_all()
    seed_users_from_env(db.session)

# Twilio setup
from twilio.rest import Client
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
# Twilio send_sms() function
def send_sms(to, body):
    client.messages.create(
        to=to,
        from_=TWILIO_PHONE_NUMBER,
        body=body
    )

# Register send_sms with scheduler
from scheduler import set_send_sms_function
set_send_sms_function(send_sms)

start_scheduler()

@app.route('/')
def index():
    chores = Chore.query.order_by(Chore.due_date).all()
    return render_template('index.html', chores=chores)

@app.route('/completed')
def completed():
    chores = get_completed_chores()
    return render_template('completed.html', chores=chores)

@app.route('/complete/<int:chore_id>')
def complete_chore(chore_id):
    chore = Chore.query.get_or_404(chore_id)
    chore.completed = True
    db.session.commit()

    # Notify admins
    notify_admins(f"Chore '{chore.name}' marked as complete by {chore.assigned_to.name if chore.assigned_to else 'an unknown user'}.")
    flash('Chore marked as complete!')
    return redirect(url_for('index'))

@app.route('/unassigned')
def unassigned():
    chores = get_unassigned_chores()
    return render_template('unassigned.html', chores=chores)

@app.route('/history')
def history():
    history = get_chore_history()
    return render_template('history.html', history=history)

@app.route('/add', methods=['GET', 'POST'])
def add_chore():
    users = User.query.all()
    if request.method == 'POST':
        name = request.form['name']
        assigned_to_id = request.form.get('assigned_to') or None
        assigned_to = User.query.get(assigned_to_id) if assigned_to_id else None
        due_date = request.form.get('due_date')
        recurrence = request.form.get('recurrence')

        new_chore = Chore(
            name=name,
            assigned_to=assigned_to,
            due_date=datetime.strptime(due_date, '%Y-%m-%d') if due_date else None,
            recurrence=recurrence
        )
        print(f"[DEBUG] Added chore: {new_chore.name} | Assigned to: {assigned_to.name if assigned_to else 'None'} | Due: {new_chore.due_date} | Recurrence: {recurrence}")
        db.session.add(new_chore)
        db.session.commit()

        if new_chore.assigned_to and new_chore.assigned_to.phone:
            send_sms(new_chore.assigned_to.phone,
                     f"New chore assigned: {new_chore.name} (due {new_chore.due_date.strftime('%b %d') if new_chore.due_date else 'someday'})")
        flash('Chore added successfully')
        return redirect(url_for('index'))
    return render_template('add_chore.html', users=users)


@app.route("/sms", methods=["POST"])
def handle_sms():
    print("[SMS ROUTE] Hit /sms endpoint")

    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "").strip()

    print(f"[SMS RECEIVED] From: {from_number} | Message: '{incoming_msg}'")

    user = get_user_by_phone(from_number)
    if not user:
        return _twiml(dusty_response("unauthorized"))

    # NLP intent + entity parsing
    intent, entities = parse_sms_nlp(incoming_msg)
    print(f"[INTENT] {intent} | [ENTITIES] {entities}")

    if intent == "add":
        chore_name = entities.get("chore")
        
        assignee_name = entities.get("assignee")
        if not assignee_name:
            assignee_name = user.name  # default to self if no assignee provided
        else:
            assignee_name = get_user_by_name(assignee_name)

        due_date = entities.get("due_date")
        recurrence = entities.get("recurrence")

        if not all([chore_name, assignee_name]):
            return _twiml(dusty_response("add_invalid"))

        assignee = get_user_by_name(assignee_name)
        if not assignee:
            return _twiml(dusty_response("unknown_user", extra=assignee_name))

        new_chore = Chore(
            name=chore_name,
            assigned_to_id=assignee.id,
            due_date=due_date,
            recurrence=recurrence,
        )
        db.session.add(new_chore)
        db.session.commit()

        return _twiml(dusty_response("add", extra=f"{chore_name} assigned to {assignee.name}"))

    elif intent == "done":
        chore_name = entities.get("chore")
        if not chore_name:
            return _twiml(dusty_response("done_invalid"))

        chore = Chore.query.filter(
            Chore.name.ilike(f"%{chore_name}%"),
            Chore.assigned_to_id == user.id,
            Chore.completed == False
        ).first()

        if not chore:
            return _twiml(dusty_response("not_found", extra=chore_name))

        chore.completed = True
        chore.completed_at = datetime.utcnow()
        db.session.commit()

        notify_admins(chore, user)
        return _twiml(dusty_response("done", extra=chore.name))

    elif intent == "list":
        chores = list_user_chores(user)
        if chores:
            reply = "\n".join([
                f"- {c.name} (due {c.due_date.strftime('%Y-%m-%d') if c.due_date else 'no due date'})"
                for c in chores
            ])
            return _twiml(dusty_response("list", extra=reply))
        else:
            # No assigned chores, suggest unassigned
            unassigned = get_unassigned_chores()
            if unassigned:
                options = "\n".join([f"- {c.name} (due {c.due_date.strftime('%Y-%m-%d') if c.due_date else 'no due date'})" for c in unassigned])
                return _twiml(dusty_response("no_chores") + f'\nYou can claim one of these unassigned chores:\n{options}\nReply with "claim <chore name>" to claim one.')
            else:
                return _twiml(dusty_response("no_chores"))

    elif intent == "claim":
        chore_name = entities.get("chore", "").strip(). lower()
        chore = Chore.query.filter(
            Chore.name.ilike(f"%{chore_name}%"),
            Chore.assigned_to_id == None,  # must be unassigned
        ).first()

        if chore:
            chore.assigned_to_id = user.id
            db.session.commit()

            return _twiml(dusty_response("claim", chore=chore.name, name=user.name))
        else:
            return _twiml(dusty_response("claim_fail", chore=chore_name))
        
    elif intent == "help":
        return _twiml(dusty_response("help"))

    elif intent == "greetings":
        return _twiml(dusty_response("greetings"))
    # Unknown or unsupported intent
    return _twiml(dusty_response("unknown"))
    



def _twiml(text):
    """Wrap Dusty's reply in a Twilio MessagingResponse."""
    print(f"[Dusty Replying] {text}")
    resp = MessagingResponse()
    resp.message(text)
    return str(resp)


if __name__ == '__main__':
    app.run(debug=True)