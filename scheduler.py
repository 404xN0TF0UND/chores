from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from utils import dusty_response, get_due_chores_message
from models import db, Chore
from sqlalchemy import and_

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


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=job_check_due_chores, trigger="interval", hours=1)
    scheduler.start()