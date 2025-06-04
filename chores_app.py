from flask import Flask, request, render_template, redirect, url_for
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime, timedelta
from fuzzywuzzy import fuzz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from scheduler import BackgroundScheduler
import re
import dateparser
from models import db, Chore, ConversationState
from utils import (
    USERS, ADMINS, get_user_by_phone, get_phone_by_user,
    parse_due_date, get_recurrence, send_sms, dusty_response, get_intent
)
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chores.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)


class ChoresApp:
    def __init__(self, app):
        self.app = app
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()

    def start_scheduler(self):
        self.scheduler.add_job(self.send_due_reminders, 'interval', hours=1)

    def send_due_reminders(self):
        now = datetime.now()
        with self.app.app_context():
            due_chores = Chore.query.filter(
                Chore.due_date <= now,
                Chore.completed == False
            ).all()
            users_notified = set()
            for chore in due_chores:
                if chore.assigned_user and chore.assigned_user not in users_notified:
                    chores = Chore.query.filter_by(assigned_user=chore.assigned_user, completed=False).all()
                    message = "Dusty here. These chores are due:\n" + "\n".join([f"• {c.name} (due {c.due_date.strftime('%Y-%m-%d')})" for c in chores[:5]])
                    send_sms(get_phone_by_user(chore.assigned_user), message)
                    users_notified.add(chore.assigned_user)

    def complete_chore(self, name, user):
        with self.app.app_context():
            chores = Chore.query.filter_by(assigned_user=user, completed=False).all()
            best_match = None
            highest_score = 0
            for chore in chores:
                score = fuzz.partial_ratio(chore.name.lower(), name.lower())
                if score > highest_score:
                    best_match = chore
                    highest_score = score
            if best_match and highest_score > 70:
                best_match.completed = True
                db.session.commit()

                # Notify admins
                for admin in ADMINS:
                    if admin != user:
                        phone = get_phone_by_user(admin)
                        if phone:
                            send_sms(phone, f"{user} completed '{best_match.name}'. Dusty approves.")
                return True, best_match.name
            return False, None

    def complete_chore_by_sms(self, phone_number):
        user = get_user_by_phone(phone_number)
        if not user:
            return "Hmm, you’re not on the list. Dusty only works for the registered."

        with self.app.app_context():
            chores = Chore.query.filter_by(assigned_user=user, completed=False).all()
            if not chores:
                return "You have no chores to complete. Enjoy your freedom… for now."

            chores[0].completed = True
            db.session.commit()
            return f"Marked '{chores[0].name}' as completed. Dusty tips his hat."

    def handle_add_chore(self, body, user):
        pattern = re.compile(r'add (.+?) to (\w+) due (.+)', re.IGNORECASE)
        match = pattern.search(body)
        if not match:
            return dusty_response("add_fail")

        chore_name, assigned_to, due_text = match.groups()
        assigned_to = assigned_to.strip().capitalize()
        if assigned_to not in USERS:
            return f"Sorry, I don’t know who {assigned_to} is."

        parsed_date = dateparser.parse(due_text)
        if not parsed_date:
            return "Couldn’t understand the due date. Try something like 'tomorrow'."

        recurrence = get_recurrence(body)
        new_chore = Chore(
            name=chore_name.strip(),
            assigned_user=assigned_to,
            due_date=parsed_date,
            completed=False,
            recurrence=recurrence
        )
        with self.app.app_context():
            db.session.add(new_chore)
            db.session.commit()
        return f"Chore '{chore_name.strip()}' added for {assigned_to}, due {parsed_date.strftime('%Y-%m-%d')}."

chores_app = ChoresApp(app)
chores_app.start_scheduler()


@app.route("/sms", methods=["POST"])
def sms_reply():
    body = request.form['Body'].strip()
    from_number = request.form['From']
    response = MessagingResponse()
    intent = get_intent(body)
    user = get_user_by_phone(from_number)

    if not user:
        response.message(dusty_response("unknown", success=False))
        return str(response)

    print(f"SMS from {from_number}: {body}")
    print(f"Intent: {intent}")

    if intent == "help":
        response.message("Try commands like:\n- LIST\n- DONE laundry\n- DELETE laundry\n- ADD vacuum to Erica due Friday every week")
        return str(response)

    if intent == "list":
        with app.app_context():
            chores = Chore.query.filter_by(assigned_user=user, completed=False).all()
            if chores:
                chore_list = "\n".join([f"{c.name} (due {c.due_date.strftime('%Y-%m-%d')})" for c in chores[:5]])
                response.message(f"Here’s what you’ve got:\n{chore_list}")
            else:
                response.message("No chores for you right now. Dusty is impressed.")
        return str(response)

    if intent == "done":
        match = re.search(r'done (.+)', body, re.IGNORECASE)
        if match:
            chore_name = match.group(1)
            success, matched_name = chores_app.complete_chore(chore_name, user)
            if success:
                response.message(dusty_response("done_success").replace("{chore}", matched_name))
            else:
                response.message("Dusty couldn’t find that one. Try being more specific.")
        else:
            result = chores_app.complete_chore_by_sms(from_number)
            response.message(result)
        return str(response)

    if intent == "add":
        result = chores_app.handle_add_chore(body, user)
        response.message(result)
        return str(response)

    response.message("Try commands like:\n- LIST\n- DONE laundry\n- DELETE laundry\n- Add laundry to Becky due Friday every week")
    return str(response)


@app.route("/")
def index():
    with app.app_context():
        chores = Chore.query.order_by(Chore.due_date).all()
        return render_template("index.html", chores=chores)


@app.route("/complete/<int:chore_id>")
def complete_chore(chore_id):
    with app.app_context():
        chore = Chore.query.get(chore_id)
        if chore:
            chore.completed = True
            db.session.commit()
    return redirect(url_for('index'))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)