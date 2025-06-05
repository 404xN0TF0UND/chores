import os
from flask import Flask, request, render_template, redirect, url_for, flash
from twilio.twiml.messaging_response import MessagingResponse
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime
from models import db, User, Chore, ChoreHistory
from scheduler import start_scheduler
from utils import (
    seed_users_from_env,
    get_user_by_phone,
    parse_sms,
    dusty_response,
    get_assigned_chores,
    get_completed_chores,
    get_unassigned_chores,
    get_chore_history,
    complete_chore_by_name,
    notify_admins,
    get_upcoming_chores,
    list_user_chores,
    send_sms,
    parse_natural_date
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
#_______Temporary: for testing purposes only_____________________________
# @app.route('/debug/chores')
# def debug_chores():
#     chores = Chore.query.all()
#     return {
#         "total": len(chores),
#         "chores": [chore.name for chore in chores]
#     }

# @app.route('/debug/env')
# def debug_env():
#     from os import getenv
#     return {
#         "sid": getenv("TWILIO_ACCOUNT_SID"),
#         "auth": getenv("TWILIO_AUTH_TOKEN"),
#         "number": getenv("TWILIO_PHONE_NUMBER")
#     }

#___________________________________________________
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
            send_sms(new_chore.assigned_to.phone, f"New chore assigned: {new_chore.name} (due {new_chore.due_date.strftime('%b %d') if new_chore.due_date else 'someday'})")
        
        flash('Chore added successfully')
        return redirect(url_for('index'))
        
    return render_template('add_chore.html', users=users)

@app.route('/sms', methods=['POST'])
@app.route('/sms', methods=['POST'])
def handle_sms():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '').strip()

    user = get_user_by_phone(from_number)
    if not user:
        return dusty_response("I don't recognize this number. Either you're a ghost or you haven't been added to the system.")

    # Try parsing intent and entities
    intent, entities = parse_sms(incoming_msg)

    # Handle known intents
    if intent == 'add':
        chore_name = entities.get('chore_name')
        assignee_name = entities.get('assignee', user.name)
        due_date = parse_natural_date(entities.get('due_date'))
        recurrence = entities.get('recurrence')

        assignee = User.query.filter(User.name.ilike(assignee_name)).first()
        if not assignee:
            return dusty_response(f"I don't know who '{assignee_name}' is. Try again with a valid user.")

        new_chore = Chore(
            name=chore_name,
            assigned_to=assignee,
            due_date=due_date,
            recurrence=recurrence
        )
        db.session.add(new_chore)
        db.session.commit()

        notify_admins(f"{user.name} added chore '{chore_name}' for {assignee.name}.")
        return dusty_response(f"Added chore '{chore_name}' for {assignee.name}. Due: {due_date.strftime('%Y-%m-%d') if due_date else 'whenever'}.")

    elif intent == 'complete':
        chore_name = entities.get('chore_name')
        chore = complete_chore_by_name(chore_name, user)
        if chore:
            notify_admins(f"{user.name} completed '{chore.name}'.")
            return dusty_response(f"Marked '{chore.name}' complete. Gold star for you, {user.name}.")
        else:
            return dusty_response(f"No matching chore called '{chore_name}'. Maybe it's still on your to-do list of shame?")

    elif intent == 'list':
        chores = list_user_chores(user)
        if not chores:
            return dusty_response("You're gloriously chore-free.")
        chores_text = "\n".join([f"• {ch.name} (Due: {ch.due_date.strftime('%Y-%m-%d') if ch.due_date else 'anytime'})" for ch in chores[:5]])
        return dusty_response(f"Here’s your glorious list of doom:\n{chores_text}")

    elif intent == 'greeting':
        return dusty_response(f"Ah, greetings {user.name}. I trust you've been diligently ignoring your chores.")

    else:
        return dusty_response("I couldn't quite make sense of that. Try something like 'add dishes to Becky due Friday' or 'list'.")

if __name__ == '__main__':
    app.run(debug=True)