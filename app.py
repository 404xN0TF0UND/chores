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
    notify_admins(f"Chore '{chore.name}' marked as complete by {chore.assigned_to.name if chore.assigned_to else 'an unknown user'}.", twilio_client, TWILIO_PHONE_NUMBER)
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
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")
    print(f"[SMS RECEIVED] From: {from_number} | Message: '{incoming_msg}'")

    user = get_user_by_phone(from_number)
    if not user:
        return _twiml(dusty_response("unrecognized_user"))

    intent, entities = parse_sms_nlp(incoming_msg)
    print(f"[INTENT] {intent} | [ENTITIES] {entities}")

    if intent == "greeting":
        return _twiml(dusty_response("greetings", name=user.name))

    elif intent == "help":
        return _twiml(dusty_response("help"))

    elif intent == "list":
        chores = (
            Chore.query.options(joinedload(Chore.assigned_to))
            .filter_by(assigned_to_id=user.id, completed=False)
            .limit(5)
            .all()
        )
        if chores:
            chores_text = "\n".join([f"• {chore.name} (due {chore.due_date})" for chore in chores])
            response = dusty_response("list", name=user.name)
            return _twiml(f"{response}\n{chores_text}")
        else:
            unassigned = Chore.query.filter_by(assigned_to_id=None, completed=False).limit(5).all()
            if not unassigned:
                return _twiml(dusty_response("unassigned"))
            options = "\n".join([f"• {chore.name}" for chore in unassigned])
            return _twiml(f"[Dusty 🤖] You have no chores. But here are some unclaimed tasks:\n{options}")

    elif intent == "done":
        chore_name = entities.get("chore")
        if not chore_name:
            return _twiml(dusty_response("unknown"))
        chore = Chore.query.filter_by(name=chore_name, assigned_to_id=user.id, completed=False).first()
        if not chore:
            return _twiml(dusty_response("unknown"))
        chore.completed = True
        chore.completed_at = datetime.utcnow()
        db.session.commit()
        return _twiml(dusty_response("done", name=user.name, chore=chore.name))

    elif intent == "add":
        parsed = parse_sms_nlp(incoming_msg)
        if not parsed:
            return _twiml(dusty_response("add_invalid"))
        chore_name, assignee_name, due_date, recurrence = parsed
        assignee = get_user_by_name(assignee_name)
        if not assignee:
            return _twiml(dusty_response("unrecognized_user"))
        chore = Chore(name=chore_name, assigned_to=assignee, due_date=due_date, recurrence=recurrence)
        db.session.add(chore)
        db.session.commit()
        return _twiml(dusty_response("add", name=assignee.name, chore=chore_name))

    elif intent == "claim":
        chore_name = entities.get("chore")
        if not chore_name:
            return _twiml(dusty_response("unknown"))
        chore = Chore.query.filter(
            Chore.name.ilike(chore_name),
            Chore.assigned_to_id.is_(None),
            Chore.completed.is_(False)
        ).first()
        if not chore:
            return _twiml(dusty_response("unassigned"))
        chore.assigned_to_id = user.id
        db.session.commit()
        return _twiml(dusty_response("claim", name=user.name, chore=chore.name))

    return _twiml(dusty_response("unknown"))


def _twiml(text):
    """Wrap Dusty's reply in a Twilio MessagingResponse."""
    print(f"[Dusty Replying] {text}")
    resp = MessagingResponse()
    resp.message(text)
    return str(resp)


if __name__ == '__main__':
    app.run(debug=True)