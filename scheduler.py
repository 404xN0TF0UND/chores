from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime,date
from utils import dusty_response, get_due_chores_message, get_user_by_name
from models import db, Chore

from sqlalchemy import and_
import os
def send_chore_reminders(db, twilio_client):
    """Send a reminder for a specific chore"""
    today = date.today()
    due_chores = db.query(Chore).filter(
        Chore.due_date == today,
        Chore.completed == False
    ).all()

    for chore in due_chores:
        if not chore.assigned_to:
            continue
        user = get_user_by_name(db, chore.assigned_to)
        if user and user.phone:
            message = dusty_response("reminder", name=chore.assigned_to, chore=chore.name)
            response = dusty_response("reminder", name=user.name, message=message)
            twilio_client.messages.create(
                body=message,
                from_= os.getenv("TWILIO_PHONE_NUMBER"),
                to=user.phone
            )
        else:
            print(f"User {chore.assigned_to} has no phone number or is not found.")
send_sms = None  # Placeholder to be set by app.py


def set_send_sms_function(fn):
    global send_sms
    send_sms = fn


def job_check_due_chores():
    now = datetime.utcnow()
    due_chores = Chore.query.filter(
        and_(Chore.completed == False, Chore.due_date <= now)
    ).all()

    for chore in due_chores:
        if chore.assigned_to and chore.assigned_to.phone:
            message = get_due_chores_message(chore.assigned_to.name, chore.task)
            response = dusty_response("reminder", name=chore.assigned_to.name, message=message)
            send_sms(chore.assigned_to.phone, response)



def start_scheduler(db, twlio_client):
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=job_check_due_chores, trigger="interval", hours=1)
    scheduler.add_job(lambda: send_chore_reminders(db, twlio_client), trigger='interval', hours=3)
    scheduler.start()