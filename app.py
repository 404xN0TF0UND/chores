
# app.py

import os
from flask import Flask
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from models import db
from utils.users import seed_users_from_env
from services.scheduler import start_scheduler, set_send_sms_function
from routes.history import history_bp
from routes.manage import manage_bp
from routes.sms import sms_bp
from routes.misc import misc_bp
from routes.views import views_bp
from twilio.rest import Client
from services.twilio_tools import send_sms
from utils.context.store import conversation_context

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chores.db'
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "shhh")

# Initialize extensions
db.init_app(app)

# Create tables and seed users
with app.app_context():
    db.create_all()
    seed_users_from_env(db.session)

# Twilio setup
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)




set_send_sms_function(send_sms)
start_scheduler(db, twilio_client)

# Register Blueprints
app.register_blueprint(views_bp)
app.register_blueprint(history_bp)
app.register_blueprint(manage_bp)
app.register_blueprint(misc_bp)
app.register_blueprint(sms_bp)

if __name__ == "__main__":
    app.run(debug=True)
