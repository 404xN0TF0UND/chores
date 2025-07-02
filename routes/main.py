# routes/main.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Chore, ChoreHistory, User
from utils.chores import get_completed_chores, get_unassigned_chores
from utils.dusty import dusty_response
from services.twilio_tools import send_sms
from datetime import datetime, timedelta
from utils.users import get_user_by_phone
import random

main_bp = Blueprint("main", __name__)

def get_admin_user():
    return User.query.filter_by(name="Ronnie").first()

@main_bp.route('/')
def index():
    user = get_admin_user()
    chores = Chore.query.order_by(Chore.due_date).all()
    users = User.query.order_by(User.name).all()
    return render_template('index.html', chores=chores, users=users, user=user)

@main_bp.route('/completed')
def completed():
    chores = get_completed_chores()
    return render_template('completed.html', chores=chores)

@main_bp.route('/unassigned')
def unassigned():
    chores = get_unassigned_chores()
    return render_template('unassigned.html', chores=chores)

@main_bp.route('/history')
def history():
    completed_chores = ChoreHistory.query.filter(ChoreHistory.completed == True).order_by(ChoreHistory.completed_at.desc()).all()
    return render_template('history.html', chores=completed_chores)

@main_bp.route('/unassigned')
def unassigned():
    chores = get_unassigned_chores()
    return render_template('unassigned.html', chores=chores)


@main_bp.route('/delete/<int:chore_id>', methods=['POST'])
def delete_chore(chore_id):
    user = get_admin_user()
    if not user or not user.is_admin:
        flash("You're not allowed to delete chores", "danger")
        return redirect(url_for('main.index'))
    chore = Chore.query.get_or_404(chore_id)
    db.session.delete(chore)
    db.session.commit()
    flash(f"Deleted chore: {chore.name}", "success")
    return redirect(url_for('main.index'))


@main_bp.route('/unassign/<int:chore_id>', methods=['POST'])
def unassign_chore(chore_id):
    user = get_admin_user()
    if not user or not user.is_admin:
        flash("Not authorized.", "danger")
        return redirect(url_for('main.index'))
    chore = Chore.query.get_or_404(chore_id)
    chore.assigned_to_id = None
    db.session.commit()
    flash(f"Unassigned chore: {chore.name}", "info")
    return redirect(url_for('main.index'))


@main_bp.route('/reassign/<int:chore_id>', methods=['POST'])
def reassign_chore(chore_id):
    user = get_admin_user()
    if not user or not user.is_admin:
        flash("Not authorized.", "danger")
        return redirect(url_for('main.index'))
    new_user_id = request.form.get("user_id")
    chore = Chore.query.get_or_404(chore_id)
    chore.assigned_to_id = new_user_id
    db.session.commit()

    assignee = User.query.get(new_user_id)
    if assignee and assignee.phone:
        sass = dusty_response("reassigned", name=assignee.name, extra=chore.name)
        send_sms(assignee.phone, f"[Dusty 🤖] {sass}")
    flash(f"Reassigned chore: {chore.name}", "info")
    return redirect(url_for('main.index'))


@main_bp.route('/snooze/<int:chore_id>', methods=['POST'])
def snooze_chore(chore_id):
    user = get_admin_user()
    if not user or not user.is_admin:
        flash("Not authorized.", "danger")
        return redirect(url_for('main.index'))
    chore = Chore.query.get_or_404(chore_id)
    if not chore.due_date:
        flash(f"Chore '{chore.name}' has no due date to snooze.", "warning")
        return redirect(url_for('main.index'))
    chore.due_date += timedelta(days=7 if chore.recurrence == 'weekly' else 1)
    db.session.commit()
    flash(f"Snoozed chore '{chore.name}' to {chore.due_date.strftime('%Y-%m-%d')}.", "info")
    return redirect(url_for('main.index'))