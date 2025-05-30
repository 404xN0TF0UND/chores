import json
import os
import re
import dateparser
from datetime import datetime , timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from twilio.base.exceptions import TwilioRestException
from dotenv import load_dotenv
load_dotenv()

# Twilio configuration (replace with your credentials)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
print(f"Loaded TWILLIO_PHONE_NUMBER: {TWILIO_PHONE_NUMBER}")

# File to store chore and user data
DATA_FILE = "chores.json"

# Initialize users with phone numbers (for SMS)
USERS = {
    "Ronnie": "+17173770285",
    "Becky": "+12405294440",
    "Dan": "+12234260451",
    "Cait": "+17173870963",
    "Toby": "+17173876892",
    "Erica": "+17173774563"
}

# Initialize Twilio client
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Chore management class
class ChoresApp:
    def __init__(self):
        self.chores = []
        self.load_data()

    def load_data(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                self.chores = json.load(f)

    def save_data(self):
        with open(DATA_FILE, 'w') as f:
            json.dump(self.chores, f, indent=4)

    def add_chore(self, name, due_date, assigned_user=None, recurrence=None):
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
            chore = {
                "id": len(self.chores) + 1,
                "name": name,
                "due_date": due_date,
                "assigned_user": assigned_user,
                "completed": False,
                "recurrence": recurrence  # New
            }
            self.chores.append(chore)
            self.save_data()
            if assigned_user:
                self.send_sms(assigned_user, f"You've been assigned: {name}, due {due_date}")
            return True, "Chore added successfully."
        except ValueError:
            return False, "Invalid date format. Use YYYY-MM-DD."

    def assign_chore(self, chore_id, user):
        if user and user not in USERS:
            return False, f"User '{user}' does not exist."
        for chore in self.chores:
            if chore["id"] == chore_id:
                old_user = chore["assigned_user"]
                chore["assigned_user"] = user if user else None
                self.save_data()
                if user and user != old_user:
                    self.send_sms(user, f"You've been assigned: {chore['name']}, due {chore['due_date']}. Reply 'DONE' when completed.")
                return True, f"Chore '{chore['name']}' assigned to {user or 'Unassigned'}."
        return False, f"Chore ID {chore_id} not found."

    def complete_chore(self, chore_id):
        for chore in self.chores:
            if chore["id"] == chore_id:
                chore["completed"] = True
                self.save_data()

                # Handle recurrence
                if chore.get("recurrence"):
                    self._create_next_recurrence(chore)

                return True, f"Chore '{chore['name']}' marked as completed."
        return False, f"Chore ID {chore_id} not found."

    def _create_next_recurrence(self,chore):
        recurrence = chore.get("recurrence")
        current_due = datetime.strptime(chore["due_date"], "%Y-%m-%d")

        if recurrence == "daily":
            next_due = current_due + timedelta(days=1)
        elif recurrence == "weekly":
            next_due = current_due + timedelta(weeks=1)
        elif recurrence == "monthly":
            next_due = current_due.replace(month=current_due.month % 12 +1)
        elif recurrence.startswith("every "):
            try:
                days = int(recurrence.split()[1])
                next_due = current_due + timedelta(days=days)
            except Exception:
                return
        else:
            return
        self.add_chore(chore["name"], next_due.strftime("%Y-%m-%d"), chore["assigned_user"], recurrence)
    
    
    def complete_chore_by_sms(self, phone_number):
        # Find the user by phone number
        user = next((name for name, num in USERS.items() if num == phone_number), None)
        if not user:
            return False, "User not found for this phone number."
        
        # Find the most recent pending chore for the user
        user_chores = [chore for chore in self.chores if chore["assigned_user"] == user and not chore["completed"]]
        if not user_chores:
            return False, "No pending chores found."
        
        # Sort by ID (most recent chore has highest ID)
        latest_chore = max(user_chores, key=lambda x: x["id"])
        latest_chore["completed"] = True
        self.save_data()
        return True, f"Chore '{latest_chore['name']}' marked as completed by {user}."

    def send_sms(self, user, message):
        if not user or user not in USERS:
            return
        phone_number = USERS[user]
        try:
            twilio_client.messages.create(
                body=message,
                from_=TWILIO_PHONE_NUMBER,
                to=phone_number
            )
            print(f"SMS sent to {user} ({phone_number}): {message}")
        except TwilioRestException as e:
            print(f"Failed to send SMS to {user}: {e}")

    def get_chores(self, user=None, show_all=False):
        return [
            chore for chore in self.chores
            if (show_all or not chore["completed"]) and (user is None or chore["assigned_user"] == user)
        ]

    def get_unassigned_chores(self):
        return [chore for chore in self.chores if not chore["assigned_user"] and not chore["completed"]]

# Initialize Flask app
app = Flask(__name__)
app.secret_key = "supersecretkey"
chores_app = ChoresApp()

# Routes (same as before, with SMS webhook added)
@app.route('/')
def index():
    return render_template('index.html', users=USERS.keys())

@app.route('/chores')
def list_chores():
    user = request.args.get('user')
    show_all = request.args.get('show_all') == 'true'
    chores = chores_app.get_chores(user=user, show_all=show_all)
    return render_template('chores.html', chores=chores, users=USERS.keys(), selected_user=user)

@app.route('/unassigned')
def unassigned_chores():
    chores = chores_app.get_unassigned_chores()
    return render_template('unassigned.html', chores=chores)

@app.route('/add', methods=['GET', 'POST'])
def add_chore():
    if request.method == 'POST':
        name = request.form['name']
        due_date = request.form['due_date']
        assigned_user = request.form.get('assigned_user', '')
        success, message = chores_app.add_chore(name, due_date, assigned_user or None)
        if success:
            flash(message, 'success')
            return redirect(url_for('list_chores'))
        else:
            flash(message, 'error')
    return render_template('add_chore.html', users=USERS.keys())

@app.route('/assign/<int:chore_id>', methods=['GET', 'POST'])
def assign_chore(chore_id):
    if request.method == 'POST':
        user = request.form.get('user', '')
        success, message = chores_app.assign_chore(chore_id, user)
        if success:
            flash(message, 'success')
            return redirect(url_for('list_chores'))
        else:
            flash(message, 'error')
    chore = next((c for c in chores_app.chores if c["id"] == chore_id), None)
    if not chore:
        flash(f"Chore ID {chore_id} not found.", 'error')
        return redirect(url_for('list_chores'))
    return render_template('assign_chore.html', chore=chore, users=USERS.keys())

@app.route('/complete/<int:chore_id>')
def complete_chore(chore_id):
    success, message = chores_app.complete_chore(chore_id)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    return redirect(url_for('list_chores'))

@app.route('/sms', methods=['POST'])
def sms_reply():
    from_number = request.form.get('From')
    body = request.form.get('Body', '').strip()

    response = MessagingResponse()

    if body.upper() == "DONE":
        success, message = chores_app.complete_chore_by_sms(from_number)
        response.message(message)
        return str(response)

    # Regex to capture: add <chore> to <user> due <date> every <X>
    add_pattern = re.compile(
        r'add\s+(.+?)\s+to\s+(\w+)(?:\s+due\s+(.+?))?(?:\s+every\s+(.+))?$',
        re.IGNORECASE
    )

    match = add_pattern.match(body)
    if match:
        chore_name, user, due_text, recurrence_text = match.groups()
        user = user.capitalize()

        if user not in USERS:
            response.message(f"Unknown user '{user}'.")
            return str(response)

        # Handle due date
        if due_text:
            parsed_date = dateparser.parse(due_text)
        else:
            parsed_date = datetime.now() + timedelta(days=1)

        if not parsed_date:
            response.message("Couldn't understand the due date. Try 'YYYY-MM-DD' or natural dates like 'next Friday'.")
            return str(response)

        due_date = parsed_date.strftime("%Y-%m-%d")

        # Normalize recurrence
        recurrence = None
        if recurrence_text:
            recurrence_text = recurrence_text.lower().strip()
            if recurrence_text in ["day", "daily"]:
                recurrence = "daily"
            elif recurrence_text in ["week", "weekly"]:
                recurrence = "weekly"
            elif recurrence_text in ["month", "monthly"]:
                recurrence = "monthly"
            elif recurrence_text.isdigit():
                recurrence = f"every {recurrence_text}"
            elif re.match(r"every \d+", f"every {recurrence_text}"):
                recurrence = f"every {recurrence_text}"

        success, message = chores_app.add_chore(
            chore_name.strip(),
            due_date,
            assigned_user=user,
            recurrence=recurrence
        )
        response.message(message)
        return str(response)

    response.message("Please reply with 'DONE' to mark your latest chore as completed. Or try 'add vacuum to Erica due tomorrow every week'.")
    return str(response)



    

 

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))