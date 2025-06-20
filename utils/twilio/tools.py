# utils/twilio/tools.py

import os
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def send_sms(to: str, body: str):
    client.messages.create(
        to=to,
        from_=TWILIO_PHONE_NUMBER,
        body=body
    )

def _twiml(text: str) -> str:
    print(f"[Dusty Replying] {text}")
    resp = MessagingResponse()
    resp.message(text)
    return str(resp)