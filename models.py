from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime
from sqlalchemy.orm import relationship
from . import db


db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    phone_number = Column(String, unique=True, nullable=False)
    is_admin = Column(db.Boolean, default=False)
    last_roasted_at = Column(DateTime, nullable=True)

    # Relationships
    chores = relationship('Chore', back_populates="assigned_to")

    def __repr__(self):
        return f"<User {self.name}>"

class Chore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(120), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    assigned_to = db.relationship('User', backref='chores')
    due_date = db.Column(db.Date, nullable=True)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    recurrence = db.Column(db.String(20), nullable=True)  # e.g., 'daily', 'weekly', 'every 3'

    def __repr__(self):
        return f"<Chore {self.description}>"

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False, unique=True)
    state = db.Column(db.String(100), nullable=True)
    context = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Conversation {self.phone_number}>"

class ChoreHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chore_id = db.Column(db.Integer, db.ForeignKey('chore.id'))
    chore = db.relationship('Chore', backref='history')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User')
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ChoreHistory {self.chore_id} by {self.user_id}>"