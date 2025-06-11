from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    
    # New memory fields
    total_chores_completed = db.Column(db.Integer, default=0)
    total_list_requests = db.Column(db.Integer, default=0)
    favorite_chore = db.Column(db.String(100), nullable=True)
    
    
    chores = db.relationship('Chore', backref='assigned_to', lazy=True)
    history = db.relationship('ChoreHistory', backref='user', lazy=True)
    last_intent = db.Column(db.String(50), nullable=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    stats = db.relationship('ChoreStats', backref='user', lazy=True)
   
    
    def __repr__(self):
        return f"<User {self.name}>"

class Chore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    recurrence = db.Column(db.String(20), nullable=True)  # e.g. 'daily', 'weekly', etc.
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Chore {self.name}>"

class ChoreHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chore_name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    times_completed = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=True)
    def __repr__(self):
        return f"<ChoreHistory {self.chore_name} by {self.user.name}>"
    

  
class ChoreStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    chore_name = db.Column(db.String(100), nullable=False)
    times_completed = db.Column(db.Integer, default=1)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'chore_name', name='unique_user_chore'),
    )

    def __repr__(self):
        return f"<ChoreStats {self.chore_name} by {self.user.name}: {self.completion_count}>"
