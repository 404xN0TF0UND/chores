# scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from utils import send_due_reminders, cleanup_conversations

def start_scheduler():
    scheduler = BackgroundScheduler()

    # Send chore reminders every day at 8:00 AM
    scheduler.add_job(
        func=send_due_reminders,
        trigger=CronTrigger(hour=8, minute=0),
        id='daily_reminder_job',
        replace_existing=True
    )

    # Clean up expired conversations every day at 12:00 AM
    scheduler.add_job(
        func=cleanup_conversations,
        trigger=CronTrigger(hour=0, minute=0),
        id='conversation_cleanup_job',
        replace_existing=True
    )

    scheduler.start()
    print("Scheduler started with reminder and cleanup jobs.")