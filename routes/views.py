# routes/views.py
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from models import db, Chore, User
from routes.admin import get_admin_user
from utils.dusty import dusty_response
from utils.chores import get_completed_chores
from services.twilio_tools import send_sms

views_bp = Blueprint('views', __name__)

@views_bp.route('/')
def index():
    user = get_admin_user()
    chores = Chore.query.order_by(Chore.due_date).all()
    users = User.query.order_by(User.name).all()
    return render_template('index.html', chores=chores, users=users, user=user)

@views_bp.route('/completed')
def completed():
    chores = get_completed_chores()
    return render_template('completed.html', chores=chores)

@views_bp.route('/add', methods=['GET', 'POST'])
def add_chore():
    users = User.query.all()
    if request.method == 'POST':
        name = request.form['name']
        assigned_to_id = request.form.get('assigned_to') or None
        assigned_to = User.query.get(assigned_to_id) if assigned_to_id else None
        due_date = request.form.get('due_date')
        recurrence = request.form.get('recurrence')

        new_chore = Chore(
            name=name,
            assigned_to=assigned_to,
            due_date=datetime.strptime(due_date, '%Y-%m-%d') if due_date else None,
            recurrence=recurrence
        )

        db.session.add(new_chore)
        db.session.commit()

        if new_chore.assigned_to and new_chore.assigned_to.phone:
            send_sms(
                new_chore.assigned_to.phone,
                dusty_response("assigned", name=new_chore.assigned_to.name, extra=f"{new_chore.name} (due {new_chore.due_date.strftime('%b %d') if new_chore.due_date else 'someday'})", user=new_chore.assigned_to)
            )

        flash('Chore added successfully')
        return redirect(url_for('views.index'))

    return render_template('add_chore.html', users=users)
      
