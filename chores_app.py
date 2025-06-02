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
    "Ronnie": "+17173770285",
    "Becky": "+12405294440",
    "Dan": "+12234260451",
    "Cait": "+17173870963",
    "Toby": "+17173876892",
    "Erica": "+17173774563"
}

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Persistent context tracker
state_tracker = {}

def clear_old_states():
    now = datetime.utcnow()
    stale_keys = [k for k, v in state_tracker.items() if (now - v['last_updated']).total_seconds() > 86400]
    for k in stale_keys:
        del state_tracker[k]

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
    user = next((name for name, num in USERS.items() if num == from_number), None)
    if not user:
        response.message("Your phone number isn't registered.")
        return str(response)

    clear_old_states()
    state = state_tracker.get(from_number, {"context": {}, "last_updated": datetime.utcnow()})
    state["last_updated"] = datetime.utcnow()
    lower_body = body.lower()

    # LIST
    if lower_body == "list":
        chores = chores_app.get_chores(user=user)
        if not chores:
            response.message("You have no chores assigned.")
        else:
            msg = "Your chores:\n" + "\n".join(f"- {c.name} (due {c.due_date})" for c in chores[:5])
            response.message(msg)
        return str(response)

    # DONE <chore>
    done_match = re.match(r"done\s+(.+)", body, re.IGNORECASE)
    if done_match:
        target = done_match.group(1).strip().lower()
        user_chores = chores_app.get_chores(user=user, show_all=True)
        matching = [c for c in user_chores if target in c.name.lower()]
        if not matching:
            response.message(f"No matching chore named '{target}'.")
        elif len(matching) > 1:
            response.message("Multiple matches: " + ", ".join(c.name for c in matching))
        else:
            chores_app.complete_chore(matching[0].id)
            response.message(f"Completed: {matching[0].name}")
        return str(response)

    # ADD flow using state
    if lower_body.startswith("add"):
        add_match = re.match(r"add\s+(.*?)\s+to\s+(\w+)(?:\s+due\s+(.+?))?(?:\s+every\s+(.+))?$", lower_body)
        if add_match:
            name, assignee, due_text, recur_text = add_match.groups()
            if assignee.capitalize() not in USERS:
                response.message(f"Unknown user '{assignee}'.")
                return str(response)
            due = dateparser.parse(due_text) if due_text else datetime.now() + timedelta(days=1)
            if not due:
                response.message("Invalid due date. Try 'tomorrow' or '2025-06-01'.")
                return str(response)
            recurrence = None
            if recur_text:
                if recur_text in ["day", "daily"]: recurrence = "daily"
                elif recur_text in ["week", "weekly"]: recurrence = "weekly"
                elif recur_text in ["month", "monthly"]: recurrence = "monthly"
                elif recur_text.isdigit(): recurrence = f"every {recur_text} days"
            success, msg = chores_app.add_chore(name, due.strftime("%Y-%m-%d"), assignee.capitalize(), recurrence)
            response.message(msg)
            return str(response)

    response.message("Try:\n- LIST\n- DONE laundry\n- ADD trash to Becky due tomorrow every week")
    return str(response)

@app.route('/')
def index():
    chores = chores_app.get_chores(show_all=True)
    return render_template('index.html', chores=chores, users=USERS)

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