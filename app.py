import os
from flask import Flask, request, render_template, redirect, url_for, flash
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime
from models import db, User, Chore, ChoreHistory
from scheduler import start_scheduler
from utils import (
    seed_users_from_env, get_user_by_phone, parse_sms,
    dusty_response, get_assigned_chores, get_completed_chores,
    get_unassigned_chores, get_chore_history, complete_chore_by_name,
    notify_admins, get_upcoming_chores, list_user_chores,
    parse_natural_date
)

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
        due_date = request.form.get('due_date')
        recurrence = request.form.get('recurrence')

        new_chore = Chore(
            name=name,
            assigned_to_id=assigned_to_id,
            due_date=datetime.strptime(due_date, '%Y-%m-%d') if due_date else None,
            recurrence=recurrence
        )
        db.session.add(new_chore)
        db.session.commit()

        if new_chore.assigned_to and new_chore.assigned_to.phone:
            send_sms(new_chore.assigned_to.phone,
                     f"New chore assigned: {new_chore.name} (due {new_chore.due_date.strftime('%b %d') if new_chore.due_date else 'someday'})")
        flash('Chore added successfully')
        return redirect(url_for('index'))
    return render_template('add_chore.html', users=users)

@app.route('/sms', methods=["POST"])
def handle_sms():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '').strip()

    print(f"[SMS] From: {from_number}, Message: {incoming_msg}")

    user = get_user_by_phone(from_number)
    if not user:
        return dusty_response("unrecognized_user")

    intent, entities = parse_sms(incoming_msg)
    print(f"[PARSER] Intent: {intent}, Entities: {entities}")

    # --- ADD CHORE ---
    if intent == 'add':
        chore_name = entities.get('chore_name')
        if not chore_name:
            return dusty_response("You're trying to add... something. Care to specify what?")

        assignee_name = entities.get('assignee') or user.name
        assignee = User.query.filter(User.name.ilike(assignee_name)).first()
        if not assignee:
            return dusty_response(f"Nice try, but I don't know who '{assignee_name}' is.")

        due_date = parse_natural_date(entities.get('due_date'))
        recurrence = entities.get('recurrence')

        new_chore = Chore(
            name=chore_name,
            assigned_to=assignee,
            due_date=due_date,
            recurrence=recurrence
        )
        db.session.add(new_chore)
        db.session.commit()

        notify_admins(
            f"{user.name} added chore \"{chore_name}\" assigned to {assignee.name} (due: {due_date.strftime('%Y-%m-%d') if due_date else 'anytime'}).",
            
        )
        print("[DEBUG] Returning success response for add.")
        return dusty_response("add", name=user.name)

    # --- COMPLETE CHORE ---
    elif intent == 'complete':
        chore_name = entities.get('chore_name')
        if not chore_name:
            return dusty_response("Finish what? Be specific, my circuits can't guess.")
        chore = complete_chore_by_name(chore_name, user)
        if chore:
            notify_admins(f"{user.name} completed '{chore.name}'.", twilio_client, TWILIO_PHONE_NUMBER)
            return dusty_response("done", name=user.name)
        else:
            return dusty_response(f"No chore named '{chore_name}' found for you. Delusional much?")

    # --- LIST CHORES ---
    elif intent == 'list':
        chores = list_user_chores(user)
        if not chores:
            return dusty_response("You're gloriously chore-free.")
        chores_text = "\n".join([
            f"• {ch.name} (Due: {ch.due_date.strftime('%Y-%m-%d') if ch.due_date else 'anytime'})"
            for ch in chores[:5]
        ])
        return dusty_response("list", name=user.name, extra=chores_text)

    # --- GREETINGS ---
    elif intent == 'greeting':
        return dusty_response("greetings", name=user.name)

    # --- HELP ---
    elif intent == 'help':
        return dusty_response(
            "Try commands like:\n"
            "• add dishes to Becky due Friday\n"
            "• done laundry\n"
            "• list"
        )

    # --- UNKNOWN ---
    return dusty_response("unknown", name=user.name)


if __name__ == '__main__':
    app.run(debug=True)