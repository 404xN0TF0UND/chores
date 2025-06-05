from apscheduler.schedulers.background import BackgroundScheduler
from utils import send_reminders, clean_conversations

def start_scheduler(app):
    scheduler_instance = BackgroundScheduler()

    # Job: Send SMS reminders daily at 9:00 AM
    scheduler_instance.add_job(
        func=lambda: send_reminders(app),
        trigger='cron',
        hour=9,
        minute=0,
        id='daily_reminders'
    )

    # Job: Clean up old conversation states every hour
    scheduler_instance.add_job(
        func=lambda: clean_conversations(app),
        trigger='cron',
        minute=0,
        id='conversation_cleanup'
    )

    scheduler_instance.start()
    print("Scheduler started with daily reminders and hourly cleanup.")

# This is what you import in chores_app.py:
# from scheduler import start_scheduler