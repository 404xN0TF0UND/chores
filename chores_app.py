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
    send_sms
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
@app.route('/debug/chores')
def debug_chores():
    chores = Chore.query.all()
    return {
        "totoal": len(chores),
        "chores": [chore.name for chore in chores]
    }

@app.route('/debug/env')
def debug_env():
    from os import getenv
    return {
        "sid": getenv("TWILIO_ACCOUNT_SID"),
        "auth": getenv("TWILIO_AUTH_TOKEN"),
        "number": getenv("TWILIO_PHONE_NUMBER")
    }

#___________________________________________________
@app.route('/')
def index():
    chores = get_assigned_chores(user_id=None)  # None for all users
    return render_template('index.html', chores=chores)

@app.route('/completed')
def completed():
    chores = get_completed_chores()
    return render_template('completed.html', chores=chores)

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
def sms_reply():
      incoming_msg = request.values.get('Body', '').strip()
      from_number = request.values.get('From', '')
      user = get_user_by_phone(from_number)

      resp = MessagingResponse()

      if not user:
        resp.message("Sorry, I don't recognize this number. Contact an admin.")
        return str(resp)

      intent, data = parse_sms(incoming_msg)

    # Route intents
      if intent == 'list_chores':
        chores = list_user_chores(user.id)
        if not chores:
            msg = "You’ve got nothing. Either you’re lucky or lazy. Probably the latter."
        else:
            msg = "\n".join([f"• {chore.name} (due {chore.due_date.strftime('%b %d') if chore.due_date else 'someday'})" for chore in chores])
        resp.message(dusty_response(msg))
      elif intent == 'complete_chore':
        chore_name = data.get('chore_name')
        result = complete_chore_by_name(user.id, chore_name)
        if result:
            msg = f"Nice, {chore_name} marked done. Applause. Confetti. Sarcasm."
            notify_admins(f"{user.name} just finished: {chore_name}")
        else:
            msg = f"I looked. No '{chore_name}' found for you. Try again?"
        resp.message(dusty_response(msg))
      elif intent == 'add_chore':
        # Future support for "add chore" via SMS
        resp.message(dusty_response("Chore creation via SMS isn’t available yet. Try the web UI."))
      else:
        resp.message(dusty_response("Try saying something like LIST or DONE mop. Dusty isn’t psychic… yet."))

      return str(resp)

if __name__ == '__main__':
    app.run(debug=True)