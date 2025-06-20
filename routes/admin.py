# routes/admin.py
from flask import Blueprint, request, redirect, url_for, flash
from models import db, Chore, User
from utils.dusty import dusty_response
from services.twilio_tools import send_sms
from datetime import timedelta
import random

admin_bp = Blueprint("admin", __name__)

def get_admin_user():
    return User.query.filter_by(name="Ronnie").first()

@admin_bp.route('/delete/<int:chore_id>', methods=['POST'])
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

@admin_bp.route('/unassign/<int:chore_id>', methods=['POST'])
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

@admin_bp.route('/reassign/<int:chore_id>', methods=['POST'])
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
        sass = random.choice([
            f"Guess who got voluntold? Yep, it's you. '{chore.name}' is now your problem.",
            f"Congratulations! You've been *upgraded* to the proud owner of chore: {chore.name}.",
            f"{chore.name} has a new home. Spoiler: it's yours now.",
            f"{chore.name} was lonely. You've been *carefully selected* to fix that."
        ])
        send_sms(assignee.phone, f"[Dusty 🤖] {sass}")

    flash(f"Reassigned chore: {chore.name}", "info")
    return redirect(url_for('main.index'))

@admin_bp.route('/snooze/<int:chore_id>', methods=['POST'])
def snooze_chore(chore_id):
    user = get_admin_user()
    if not user or not user.is_admin:
        flash("Not authorized.", "danger")
        return redirect(url_for('main.index'))

    chore = Chore.query.get_or_404(chore_id)
    if not chore.due_date:
        flash(f"Chore '{chore.name}' has no due date to snooze.", "warning")
        return redirect(url_for('main.index'))

    if chore.recurrence == 'weekly':
        chore.due_date += timedelta(days=7)
    else:
        chore.due_date += timedelta(days=1)

    db.session.commit()
    flash(f"Snoozed chore '{chore.name}' to {chore.due_date.strftime('%Y-%m-%d')}.", "info")
    return redirect(url_for('main.index'))

# Add more routes here as we continue the migration...