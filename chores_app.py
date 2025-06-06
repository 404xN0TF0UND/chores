import os
from datetime import datetime
from flask import Flask, request, render_template, redirect, url_for, flash
from dotenv import load_dotenv
from twilio.twiml.messaging_response import MessagingResponse

from models import db, User, Chore, ChoreHistory
from scheduler import start_scheduler
from utils import (
    seed_users_from_env, get_user_by_phone, parse_sms, dusty_response,
    get_assigned_chores, get_completed_chores, get_unassigned_chores,
    get_chore_history, complete_chore_by_name, notify_admins,
    get_upcoming_chores, list_user_chores, send_sms, get_intent, continue_conversation,
    update_conversation_state, get_user_by_name, conversation_state
)

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chores.db'
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "shhh")

db.init_app(app)

with app.app_context():
    db.create_all()
    seed_users_from_env()

start_scheduler(app)

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
        due_date_str = request.form.get('due_date')
        recurrence = request.form.get('recurrence')

        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d') if due_date_str else None
        except ValueError:
            flash("Invalid due date format. Please use YYYY-MM-DD.")
            return redirect(url_for('add_chore'))

        new_chore = Chore(
            name=name,
            assigned_to_id=assigned_to_id,
            due_date=due_date,
            recurrence=recurrence
        )

        db.session.add(new_chore)
        db.session.commit()

        if new_chore.assigned_to and new_chore.assigned_to.phone:
            send_sms(
                new_chore.assigned_to.phone,
                f"New chore assigned: {new_chore.name} (due {new_chore.due_date.strftime('%b %d') if new_chore.due_date else 'someday'})"
            )

        flash('Chore added successfully')
        return redirect(url_for('index'))

    return render_template('add_chore.html', users=users)


@app.route('/sms', methods=["POST"])
def handle_sms():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '').strip()
    user = get_user_by_phone(from_number)

    if not user:
        return dusty_response("I don't recognize this number. Either you're a ghost or you haven't been added to the system.")

    # 1. Continue an existing conversation?
    if from_number in conversation_state:
        intent, entities, missing = continue_conversation(from_number, incoming_msg)
        if missing:
            return dusty_response(f"Still need: {', '.join(missing)}.")
    else:
        # 2. New message — parse it
        intent = get_intent(incoming_msg)
        entities = {}
        parsed_intent, parsed_entities = parse_sms(incoming_msg)

        if parsed_intent == intent:
            entities = parsed_entities

        # Slot check for 'add'
        if intent == "add":
            missing = []
            if not entities.get("chore_name"):
                missing.append("chore_name")
            if not entities.get("assignee"):
                missing.append("assignee")
            if not entities.get("due_date"):
                missing.append("due_date")
            if missing:
                update_conversation_state(from_number, intent, entities, missing)
                return dusty_response(f"Okay, you're trying to add a chore. What is the {' and '.join(missing)}?")

    # 3. Execute intent
    if intent == 'add':
        chore_name = entities.get("chore_name")
        assignee_name = entities.get("assignee")
        assignee = get_user_by_name(assignee_name)
        due_date = entities.get("due_date")
        recurrence = entities.get("recurrence")

        if not (chore_name and assignee and due_date):
            return dusty_response("Still missing info to add the chore. Try again.")
        
        new_chore = Chore(
            name=chore_name,
            assigned_to=assignee,
            due_date=due_date,
            recurrence=recurrence
        )
        db.session.add(new_chore)
        db.session.commit()
        notify_admins(f"{user.name} added '{chore_name}' for {assignee.name}.")
        conversation_state.pop(from_number, None)
        return dusty_response(f"Chore '{chore_name}' added for {assignee.name}. Due {due_date.strftime('%Y-%m-%d')}. Now go do it... or don’t.")

    elif intent == 'complete':
        chore_name = entities.get('chore_name')
        chore = complete_chore_by_name(chore_name, user)
        if chore:
            notify_admins(f"{user.name} completed '{chore.name}'.")
            return dusty_response(f"Marked '{chore.name}' done. You're truly an overachiever.")
        return dusty_response(f"Couldn't find '{chore_name}'. Did you imagine it?")

    elif intent == 'list':
        chores = list_user_chores(user)
        if not chores:
            return dusty_response("You're chore-free. For now.")
        chores_text = "\n".join([f"• {c}" for c in chores])
        return dusty_response(f"Here's your current doom:\n{chores_text}")

    elif intent == 'greeting':
        return dusty_response(f"Ah, greetings {user.name}. I trust you've been diligently ignoring your chores.")

    return dusty_response("I'm not sure what you're trying to say. Try something like 'add laundry to Becky due Friday'.")

if __name__ == '__main__':
    app.run(debug=True)