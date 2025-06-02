
    
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

db = SQLAlchemy()

class Chore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    due_date = db.Column(db.String(20), nullable=False)
    assigned_user = db.Column(db.String(50), nullable=True)
    completed = db.Column(db.Boolean, default=False)
    recurrence = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f'<Chore {self.name} due {self.due_date} assigned to {self.assigned_user}>'

class ConversationState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    last_updated = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_command = db.Column(db.String(100), nullable=True)
    pending_chore_name = db.Column(db.String(100), nullable=True)
    pending_due_date = db.Column(db.String(20), nullable=True)
    pending_recurrence = db.Column(db.String(50), nullable=True)
    pending_user = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f'<ConversationState for {self.phone_number}>'