# services/scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from models import Chore, User
from sqlalchemy.orm import joinedload
from utils.dusty import dusty_response

scheduler = BackgroundScheduler()
send_sms_function = None  # This will be injected from the main app

def set_send_sms_function(func):
    global send_sms_function
    send_sms_function = func

def send_reminder_sms(chore, assignee):
    if not send_sms_function:
        print("[SCHEDULER] No SMS function set. Skipping reminder.")
        return

    message = dusty_response("reminder", name=assignee.name, extra=f"{chore.name} (due {chore.due_date.strftime('%Y-%m-%d')})")
    send_sms_function(assignee.phone, message)

def remind_users(db):
    print("[SCHEDULER] Checking for chores due today...")
    today = datetime.utcnow().date()
    chores_due = Chore.query.options(joinedload(Chore.assigned_to)).filter(
        Chore.due_date == today,
        Chore.completed == False,
        Chore.assigned_to_id.isnot(None)
    ).all()

    for chore in chores_due:
        assignee = chore.assigned_to
        if assignee and assignee.phone:
            send_reminder_sms(chore, assignee)

def start_scheduler(db, twilio_client=None):
    print("[SCHEDULER] Starting background scheduler...")
    scheduler.add_job(lambda: remind_users(db), "interval", hours=24)
    scheduler.start()