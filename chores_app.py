import os
import re
import dateparser
import schedule
import time
import threading
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, flash
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from twilio.base.exceptions import TwilioRestException
from dotenv import load_dotenv
from models import db, Chore, ConversationState

load_dotenv()

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

USERS = {
    key.replace("USER_", ""): value
    for key, value in os.environ.items() if key.startswith("USER_")
   }

ADMINS = ["Ronnie", "Becky"]

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Persistent context tracker
state_tracker = {}

def clear_old_states():
    now = datetime.utcnow()
    stale_keys = [k for k, v in state_tracker.items() if (now - v['last_updated']).total_seconds() > 86400]
    for k in stale_keys:
        del state_tracker[k]

def get_user_by_phone(phone_number):
    """Returns the username if the phone number is registered, else None."""
    for user, stored_number in USERS.items():
        if stored_number[-10:] == phone_number[-10:]:  # Match last 10 digits for flexibility
            return user
    return None

# Chore manager class
class ChoresApp:
    def add_chore(self, name, due_date, assigned_user=None, recurrence=None):
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
            chore = Chore(
                name=name,
                due_date=due_date,
                assigned_user=assigned_user,
                completed=False,
                recurrence=recurrence
            )
            db.session.add(chore)
            db.session.commit()
            if assigned_user:
                self.send_sms(assigned_user, f"You've been assigned: {name}, due {due_date}")
            return True, "Chore added successfully."
        except ValueError:
            return False, "Invalid date format. Use YYYY-MM-DD."

    def assign_chore(self, chore_id, user):
        if user and user not in USERS:
            return False, f"User '{user}' does not exist."
        chore = Chore.query.get(chore_id)
        if not chore:
            return False, f"Chore ID {chore_id} not found."
        old_user = chore.assigned_user
        chore.assigned_user = user
        db.session.commit()
        if user and user != old_user:
            self.send_sms(user, f"You've been assigned: {chore.name}, due {chore.due_date}")
        return True, f"Chore '{chore.name}' assigned to {user or 'Unassigned'}."

    def complete_chore(self, chore_id):
        chore = Chore.query.get(chore_id)
        if not chore:
            return False, f"Chore ID {chore_id} not found."
        
        chore.completed = True
        db.session.commit()
        
        # Notify Admins
        for admin in ADMINS:
            if chore.assigned_user and admin != chore.assigned_user:
                self.send_sms(admin, f"Chore '{chore.name}' completed by {chore.assigned_user} on {chore.due_date}.")
            else:
                # If the chore was unassigned, notify all admins
                if admin in USERS:
                    self.send_sms(admin, f"Chore '{chore.name}' completed on {chore.due_date}.")
        # Notify the assigned user if any
        if chore.assigned_user and chore.assigned_user in USERS:        
            self.send_sms(admin, f"Chore '{chore.name}' completed by {chore.assigned_user or 'Unassigned'} on {chore.due_date}.")

        # Handle recurrence
        if chore.recurrence:
            self._create_next_recurrence(chore)
        return True, f"Chore '{chore.name}' marked as completed."

    def _create_next_recurrence(self, chore):
        try:
            current_due = datetime.strptime(chore.due_date, "%Y-%m-%d")
        except ValueError:
            return
        recurrence = chore.recurrence
        next_due = None
        if recurrence == "daily":
            next_due = current_due + timedelta(days=1)
        elif recurrence == "weekly":
            next_due = current_due + timedelta(weeks=1)
        elif recurrence == "monthly":
            next_due = current_due.replace(month=(current_due.month % 12) + 1)
        elif recurrence.startswith("every "):
            parts = recurrence.split()
            try:
                interval = int(parts[1])
                if "day" in recurrence:
                    next_due = current_due + timedelta(days=interval)
                elif "week" in recurrence:
                    next_due = current_due + timedelta(weeks=interval)
                elif "month" in recurrence:
                    next_due = current_due.replace(month=(current_due.month + interval - 1) % 12 + 1)
            except (ValueError, IndexError):
                return
        if not next_due:
            return
        new_chore = Chore(
            name=chore.name,
            due_date=next_due.strftime("%Y-%m-%d"),
            assigned_user=chore.assigned_user,
            completed=False,
            recurrence=chore.recurrence
        )
        db.session.add(new_chore)
        db.session.commit()
        if chore.assigned_user:
            self.send_sms(chore.assigned_user, f"New recurrence: {new_chore.name} due {new_chore.due_date}")

    def send_sms(self, user, message):
        if user not in USERS:
            return
        try:
            twilio_client.messages.create(
                body=message,
                from_=TWILIO_PHONE_NUMBER,
                to=USERS[user]
            )
        except TwilioRestException as e:
            print(f"SMS to {user} failed: {e}")

    def get_chores(self, user=None, show_all=False):
        query = Chore.query
        if not show_all:
            query = query.filter_by(completed=False)
        if user:
            query = query.filter_by(assigned_user=user)
        return query.order_by(Chore.due_date).all()

    def get_unassigned_chores(self):
        return Chore.query.filter_by(assigned_user=None, completed=False).order_by(Chore.due_date).all()
    
    def get_user_by_phone(self, phone_number):
    #Returns the username if the phone number is registered, else None.
        for name, number in USERS.items():
            if number == phone_number:
                return name
        return None
    
    def get_chore_history(self, user=None):
        query = Chore.query.filter_by(completed=True)
        if user:
            query = query.filter_by(assigned_user=user)
            return query.order_by(Chore.updated_at.desc()).all()

app = Flask(__name__)
app.secret_key = "supersecretkey"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chores.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
with app.app_context():
    db.create_all()

chores_app = ChoresApp()

@app.route('/sms', methods=['POST'])
def sms_reply():
    from_number = request.form.get('From')
    body = request.form.get('Body', '').strip()
    response = MessagingResponse()

    # Identify user
    user = next((name for name, num in USERS.items() if num == from_number), None)
    if not user:
        response.message("Your phone number isn't registered. Contact the admin.")
        return str(response)

    # Normalize message
    message = body.lower()

    # Check existing conversation state
    state = ConversationState.query.filter_by(phone_number=from_number).first()

    # Shortcut commands
    if message == "list":
        chores = chores_app.get_chores(user=user)
        if not chores:
            response.message("You have no assigned chores.")
        else:
            reply = "Your chores:\n" + "\n".join(
                f"- {ch.name} (due {ch.due_date})" for ch in chores[:5])
            response.message(reply)
        return str(response)

    if message.startswith("done"):
        chore_name = message[5:].strip().lower()
        user_chores = chores_app.get_chores(user=user, show_all=True)
        matching = [c for c in user_chores if chore_name in c.name.lower()]
        if not matching:
            response.message(f"No chore found matching '{chore_name}'.")
        elif len(matching) > 1:
            names = ", ".join(c.name for c in matching)
            response.message(f"Multiple chores match: {names}. Be more specific.")
        else:
            chore = matching[0]
            chores_app.complete_chore(chore.id)
            response.message(f"Chore '{chore.name}' marked as completed.")
        return str(response)

    if message == "done":
        success, msg = chores_app.complete_chore_by_sms(from_number)
        response.message(msg)
        return str(response)

    # Check if continuing a previous state
    if state and state.step == "awaiting_due_date":
        parsed = dateparser.parse(message)
        if not parsed:
            response.message("Couldn't understand the due date. Try again.")
            return str(response)

        due_date = parsed.strftime("%Y-%m-%d")
        recurrence = state.recurrence if state.recurrence else None
        success, msg = chores_app.add_chore(state.chore_name, due_date, assigned_user=user, recurrence=recurrence)
        db.session.delete(state)
        db.session.commit()
        response.message(msg)
        return str(response)

    # Natural "Add chore" parser
    match = re.match(r"add\s+(.*?)\s+to\s+(\w+)(?:\s+due\s+(.+?))?(?:\s+every\s+(\w+))?$", message, re.IGNORECASE)
    if match:
        chore_name, assigned_user, due_text, recurrence_text = match.groups()
        assigned_user = assigned_user.capitalize()
        if assigned_user not in USERS:
            response.message(f"Unknown user '{assigned_user}'.")
            return str(response)

        parsed_date = dateparser.parse(due_text) if due_text else None
        if not parsed_date:
            # Ask user to clarify due date
            new_state = ConversationState(
                phone_number=from_number,
                step="awaiting_due_date",
                chore_name=chore_name,
                recurrence=recurrence_text,
                last_updated=datetime.now()
            )
            db.session.add(new_state)
            db.session.commit()
            response.message(f"When is '{chore_name}' due?")
            return str(response)

        due_date = parsed_date.strftime("%Y-%m-%d")
        recurrence = None
        if recurrence_text:
            rt = recurrence_text.lower()
            if rt in ["day", "daily"]: recurrence = "daily"
            elif rt in ["week", "weekly"]: recurrence = "weekly"
            elif rt in ["month", "monthly"]: recurrence = "monthly"
            elif rt.isdigit(): recurrence = f"every {rt}"
            elif rt.startswith("every "): recurrence = rt

        success, msg = chores_app.add_chore(chore_name, due_date, assigned_user=assigned_user, recurrence=recurrence)
        response.message(msg)
        return str(response)

    # Fallback if nothing matched
    response.message(
        "Try commands like:\n"
        "- LIST\n"
        "- DONE\n"
        "- DONE laundry\n"
        "- Add trash to Becky due tomorrow every week"
    )
    return str(response)

@app.route('/')
def index():
    chores = chores_app.get_chores(show_all=True)
    return render_template('index.html', chores=chores, users=USERS)

@app.route('/chores')
def view_chores():
    user = request.args.get('user')
    show_all = request.args.get('show_all') == 'true'
    recurrence = request.args.get('recurrence')
    due_filter = request.args.get('due')

    # Start building query
    query = Chore.query

    if user:
        query = query.filter_by(assigned_user=user)

    if not show_all:
        query = query.filter_by(completed=False)

    if recurrence:
        query = query.filter_by(recurrence=recurrence)

    if due_filter:
        today = datetime.now().date()
        if due_filter == "today":
            query = query.filter(Chore.due_date == today)
        elif due_filter == "tomorrow":
            query = query.filter(Chore.due_date == today + timedelta(days=1))
        elif due_filter == "overdue":
            query = query.filter(Chore.due_date < today, Chore.completed == False)

    chores = query.order_by(Chore.due_date).all()

    return render_template(
        'chores.html',
        chores=chores,
        users=USERS.keys(),
        selected_user=user,
        selected_recurrence=recurrence,
        selected_due_filter=due_filter,
        show_all=show_all
    )

@app.route('/add', methods=['POST'])
def add_chore_route():
    name = request.form.get('name')
    due_date = request.form.get('due_date')
    user = request.form.get('user') or None
    recurrence = request.form.get('recurrence') or None
    success, msg = chores_app.add_chore(name, due_date, user, recurrence)
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('index'))

@app.route('/complete/<int:chore_id>', methods=['POST'])
def complete_chore_route(chore_id):
    success, msg = chores_app.complete_chore(chore_id)
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('index'))

@app.route('/assign/<int:chore_id>', methods=['POST'])
def assign_chore_route(chore_id):
    user = request.form.get('user') or None
    success, msg = chores_app.assign_chore(chore_id, user)
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('index'))
def send_daily_reminders():
    for user in USERS:
        chores = chores_app.get_chores(user=user)
        if chores:
            msg = f"Good morning {user}! Your chores today:\n" + "\n".join(f"- {c.name} (due {c.due_date})" for c in chores[:5])
            chores_app.send_sms(user, msg)

@app.route('/history')
def chore_history():
    user = request.args.get('user')
    chores = chores_app.get_chore_history(user=user)
    return render_template('history.html', chores=chores, users=USERS.keys(), selected_user=user)


def start_scheduler():
    def run_schedule():
        while True:
            schedule.run_pending()
            time.sleep(60)
    # Schedule daily reminders at 8 AM
    schedule.every().day.at("08:00").do(send_daily_reminders)

    # Schedule old conversation state cleanup 
    schedule.every().day.at("00:00").do(clear_old_conversation_states)
    
    # Start the scheduler in a background thread
    thread =   threading.Thread(target=run_schedule)
    thread.daemon = True
    thread.start()

def clear_old_conversation_states():
    one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    old_states = ConversationState.query.filter(ConversationState.last_updated < one_day_ago).all()
    for state in old_states:
        db.session.delete(state)
    db.session.commit()

start_scheduler()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))