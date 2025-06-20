import os
from twilio.rest import Client
from datetime import date
from models import Chore, User

from utils.dusty.dusty import dusty_response



TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def send_sms(to, body):
    twilio_client.messages.create(to=to, from_=TWILIO_PHONE_NUMBER, body=body)


def send_chore_reminders():
    today = date.today()
    chores_due = Chore.query.filter(
        Chore.due_date == today,
        Chore.completed == False,
        Chore.assigned_to_id.isnot(None)
    ).all()

    if not chores_due:
        print("[Scheduler] No reminders to send today.")
        return

    print(f"[Scheduler] Sending {len(chores_due)} reminders...")

    for chore in chores_due:
        user = User.query.get(chore.assigned_to_id)
        if user and user.phone:
            message = dusty_response("reminder", name=user.name, chore=chore.name)
            try:
                client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                client.messages.create(
                    body=message,
                    from_=TWILIO_PHONE_NUMBER,
                    to=user.phone
                )
                print(f"[Reminder] Sent to {user.name} ({user.phone}) for chore '{chore.name}'")
            except Exception as e:
                print(f"[Reminder Error] Failed to send to {user.phone}: {e}")