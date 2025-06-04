from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    chores = db.relationship('Chore', backref='assignee', lazy=True)

    def __repr__(self):
        return f"<User {self.name}>"

class Chore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    is_completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    recurrence = db.Column(db.String(20), nullable=True)  # e.g., 'daily', 'weekly', 'every 3'

    history = db.relationship('ChoreHistory', backref='chore', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Chore {self.name} for User ID {self.assigned_to}>"

class ChoreHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chore_id = db.Column(db.Integer, db.ForeignKey('chore.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='chore_history')

    def __repr__(self):
        return f"<ChoreHistory ChoreID={self.chore_id} by UserID={self.user_id} at {self.completed_at}>"
    
class Conversation(db.Model):
    __tablename__ = 'conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False)  # Store phone number for SMS conversations
    state = db.Column(db.String(50), nullable=True)  # Conversation state
    context = db.Column(db.JSON, nullable=True)  # Store messages as JSON or text
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def update_state(self, state=None, context=None):
        if state is not None:
            self.state = state
        if context is not None:
            self.context = context
        self.last_updated = datetime.utcnow()
    def __repr__(self):
        return f"<Conversation UserID={self.user_id} at {self.created_at}>"