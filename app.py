import os
import random
from flask import Flask, request, render_template, redirect, url_for, flash
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime, timedelta
from models import db, User, Chore, ChoreHistory, ChoreStats
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import func
from scheduler import start_scheduler
from utils import (
    seed_users_from_env, get_user_by_phone, get_user_by_name,
    dusty_response, get_assigned_chores, get_completed_chores,
    get_unassigned_chores, get_chore_history, complete_chore_by_name,
    notify_admins, get_upcoming_chores, list_user_chores,
    parse_natural_date,parse_sms_nlp,memory_based_commentary
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

start_scheduler(db, twilio_client)

def get_admin_user():
    return User.query.filter_by(name="Ronnie").first()
    

@app.route('/')
def index():
    user = get_admin_user()
    chores = Chore.query.order_by(Chore.due_date).all()
    users = User.query.order_by(User.name).all()
    return render_template('index.html', chores=chores, users=users, user=user)

@app.route('/completed')
def completed():
    chores = get_completed_chores()
    return render_template('completed.html', chores=chores)

@app.route('/delete/<int:chore_id>', methods=['POST'])
def delete_chore(chore_id):
    user = get_admin_user()
    if not user or not user.is_admin:
        flash("Your not allowed to delete chores", "Danger")
        return redirect(url_for('index'))

    chore = Chore.query.get_or_404(chore_id)
    db.session.delete(chore)
    db.session.commit()
    flash(f"Deleted chore: {chore.name}", "success")
    return redirect(url_for('index'))

@app.route('/unassign/<int:chore_id>', methods=['POST'])
def unassign_chore(chore_id):
    user = get_admin_user()
    if not user or not user.is_admin:
        flash("Not authorized.", "danger")
        return redirect(url_for('index'))

    chore = Chore.query.get_or_404(chore_id)
    chore.assigned_to_id = None
    db.session.commit()
    flash(f"Unassigned chore: {chore.name}", "info")
    return redirect(url_for('index'))

@app.route('/reassign/<int:chore_id>', methods=['POST'])
def reassign_chore(chore_id):
    user = get_admin_user()
    if not user or not user.is_admin:
        flash("Not authorized.", "danger")
        return redirect(url_for('index'))

    new_user_id = request.form.get("user_id")
    chore = Chore.query.get_or_404(chore_id)
    chore.assigned_to_id = new_user_id
    db.session.commit()
    
    # Notify Reassiged User
    assignee = User.query.get(new_user_id)
    if assignee and assignee.phone:
        sass = random.choice([
            f"Guess who got voluntold? Yep, it's you. '{chore.name}' is now your problem.",
            f"Congratulations! You've been *upgraded* to the proud owner of chore: {chore.name}.",
            f"{chore.name} has a new home. Spoiler: it's yours now.",
            f"{chore.name} was lonely. You've been *carefully selected* to fix that."

        ])
        send_sms(assignee.phone, f"f[Dusty 🤖] {sass}")
    flash(f"Reassigned chore: {chore.name}", "info")
    return redirect(url_for('index'))

@app.route('/snooze/<int:chore_id>', methods=['POST'])
def snooze_chore(chore_id):
    user = get_admin_user()
    if not user or not user.is_admin:
        flash("Not authorized.", "danger")
        return redirect(url_for('index'))

    chore = Chore.query.get_or_404(chore_id)

    if not chore.due_date:
        flash(f"Chore '{chore.name}' has no due date to snooze.", "warning")
        return redirect(url_for('index'))

    # Snooze logic
    if chore.recurrence == 'weekly':
        chore.due_date += timedelta(days=7)
    else:
        chore.due_date += timedelta(days=1)

    db.session.commit()
    flash(f"Snoozed chore '{chore.name}' to {chore.due_date.strftime('%Y-%m-%d')}.", "info")
    return redirect(url_for('index'))

@app.route('/complete/<int:chore_id>')
def complete_chore(chore_id):
    chore = Chore.query.get_or_404(chore_id)
    if not chore.completed:
        chore.completed = True
        db.session.add(chore)

        # Add history entry
        if chore.assigned_to:
            history = ChoreHistory(
                chore_name=chore.name,
                user_id=chore.assigned_to.id
            )
            db.session.add(history)

        db.session.commit()
        flash(f"Chore '{chore.name}' marked as complete.", 'success')
    else:
        flash(f"Chore '{chore.name}' was already completed.", 'info')
    return redirect(url_for('index'))

@app.route('/unassigned')
def unassigned():
    chores = get_unassigned_chores()
    return render_template('unassigned.html', chores=chores)

@app.route('/history')
def history():
    completed_chores = ChoreHistory.query.filter(ChoreHistory.completed == True).order_by(ChoreHistory.completed_at.desc()).all()
    return render_template('history.html', chores=completed_chores)

@app.route("/chore-history")
def chore_history():
    # Get filter params from query string
    user_id = request.args.get("user_id", type=int)
    selected_user = request.args.get('user_id', type=int)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    query = ChoreHistory.query

    if user_id:
        query = query.filter(ChoreHistory.user_id ==user_id)

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(ChoreHistory.completed_at >= start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            query = query.filter(ChoreHistory.completed_at <= end_dt)
        except ValueError:
            pass

    history = query.order_by(ChoreHistory.completed_at.desc()).all()
    users = User.query.order_by(User.name).all()

    return render_template("chore_history.html", history=history, users=users, selected_user=selected_user,start_date=start_date,end_date=end_date)

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
    
    intent, entities = parse_sms_nlp(incoming_msg)
    print(f"[INTENT] {intent} | [ENTITIES] {entities}")

    def dusty_with_memory(key_or_text, **kwargs):
        base = dusty_response(key_or_text, **kwargs)
        memory = memory_based_commentary(user, intent)
        return f"{base} {memory}".strip()
    if not user:
        return _twiml(dusty_with_memory("unauthorized"))


# --- Memory Tracking ---
    if user:
        user.last_intent = intent
        user.last_seen = datetime.utcnow()

    if intent == "list":
        user.total_list_requests += 1

    if intent == "done" and entities.get("chore"):
        chore_name = entities["chore"].lower()
        stat = ChoreStats.query.filter_by(user_id=user.id, chore_name=chore_name).first()
        if not stat:
            stat = ChoreStats(user_id=user.id, chore_name=chore_name, times_completed=1)
            db.session.add(stat)
        else:
            stat.times_completed += 1

        # Update user's favorite chore
        favorite = (
            ChoreStats.query
            .filter_by(user_id=user.id)
            .order_by(ChoreStats.times_completed.desc())
            .first()
        )
        if favorite:
            user.favorite_chore = favorite.chore_name

    db.session.commit()

    # Update User Memory
    if user:
        user.last_seen = datetime.utcnow()
        user.last_intent = intent
        db.session.commit() 

    # NLP intent + entity parsing
    # intent, entities = parse_sms_nlp(incoming_msg)
    # print(f"[INTENT] {intent} | [ENTITIES] {entities}")

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
            return _twiml(dusty_with_memory("add_invalid",user=user.name if user else "there"))

        assignee = get_user_by_name(assignee_name)
        if not assignee:
            return _twiml(dusty_with_memory("unknown_user", extra=assignee_name))

        new_chore = Chore(
            name=chore_name,
            assigned_to_id=assignee.id,
            due_date=due_date,
            recurrence=recurrence,
        )
        db.session.add(new_chore)
        db.session.commit()

        return _twiml(dusty_with_memory("add", extra=f"{chore_name} assigned to {assignee.name}"))

    elif intent == "done":
        chore_name = entities.get("chore")
        if not chore_name:
            return _twiml(dusty_with_memory("done_invalid"))

        chore = Chore.query.filter(
            Chore.name.ilike(f"%{chore_name}%"),
            Chore.assigned_to_id == user.id,
            Chore.completed == False
        ).first()

        if not chore:
            return _twiml(dusty_with_memory("not_found", extra=chore_name, name=user.name if user else "there"))

        chore.completed = True
        chore.completed_at = datetime.utcnow()
        
        # Add history record
        history = ChoreHistory(
            chore_name=chore.name,
            user_id=user.id
        )
        db.session.add(history)
        db.session.commit()
        
        notify_admins(chore, user)
        return _twiml(dusty_with_memory("done", extra=chore.name))

    elif intent == "list":
        chores = list_user_chores(user)
        if chores:
            reply = "\n".join([
                f"- {c.name} (due {c.due_date.strftime('%Y-%m-%d') if c.due_date else 'no due date'})"
                for c in chores
            ])
            return _twiml(dusty_with_memory("list", extra=reply, name=user.name if user else "there"))
        else:
            # No assigned chores, suggest unassigned
            unassigned = get_unassigned_chores()
            if unassigned:
                options = "\n".join([f"- {c.name} (due {c.due_date.strftime('%Y-%m-%d') if c.due_date else 'no due date'})" for c in unassigned])
                return _twiml(dusty_with_memory("no_chores") + f'\nYou can claim one of these unassigned chores:\n{options}\nReply with "claim <chore name>" to claim one.')
            else:
                return _twiml(dusty_with_memory("no_chores", user=user.name if user else "there"))

    elif intent == "claim":
        chore_name = entities.get("chore", "").strip(). lower()
        chore = Chore.query.filter(
            Chore.name.ilike(f"%{chore_name}%"),
            Chore.assigned_to_id == None,  # must be unassigned
        ).first()

        if chore:
            chore.assigned_to_id = user.id
            db.session.commit()

            return _twiml(dusty_with_memory("claim", chore=chore.name, name=user.name if user else "there"))
        else:
            return _twiml(dusty_with_memory("claim_fail", chore=chore_name, name=user.name if user else "there"))
        
    elif intent == "delete":
        chore_name = entities.get("chore")
        if not chore_name:
            return _twiml(dusty_with_memory("delete_invalid", name=user.name if user else "there"))

        chore = Chore.query.filter(
        Chore.name.ilike(f"%{chore_name}%")
        ).first()

        if not chore:
            return _twiml(dusty_with_memory("not_found", extra=chore_name, name=user.name if user else "there"))

    # Check if user can delete (owner or admin)
        if not user.is_admin and chore.assigned_to_id != user.id:
            return _twiml(dusty_with_memory("unauthorized", name=user.name))

        db.session.delete(chore)
        db.session.commit()
        return _twiml(dusty_with_memory("deleted", extra=chore.name, name=user.name))
    
    elif intent == "unassign":
        chore_name = entities.get("chore")
        if not chore_name:
            return _twiml(dusty_with_memory("unassign_invalid", name=user.name))

        chore = Chore.query.filter(
        Chore.name.ilike(f"%{chore_name}%"),
        Chore.completed == False
        ).first()

        if not chore:
            return _twiml(dusty_with_memory("not_found", extra=chore_name, name=user.name))

        if not user.is_admin and chore.assigned_to_id != user.id:
            return _twiml(dusty_with_memory("unauthorized", name=user.name))

        chore.assigned_to_id = None
        db.session.commit()
        return _twiml(dusty_with_memory("unassigned", extra=chore.name, name=user.name))
    
    
    elif intent == "help":
        return _twiml(dusty_with_memory("help", name=user.name if user else "there"))

    elif intent == "greetings":
        return _twiml(dusty_with_memory("greetings", name=user.name if user else "there"))
   
  
       
     # Unknown or unsupported intent
    return _twiml(dusty_with_memory("unknown", name=user.name if user else "there"))
    
    



def _twiml(text):
    """Wrap Dusty's reply in a Twilio MessagingResponse."""
    print(f"[Dusty Replying] {text}")
    resp = MessagingResponse()
    resp.message(text)
    return str(resp)


if __name__ == '__main__':
    app.run(debug=True)