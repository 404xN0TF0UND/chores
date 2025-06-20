# routes/manage.py

from flask import Blueprint, request, render_template, redirect, url_for, flash
from datetime import datetime
import random

from models import db, Chore, User
from utils.users import get_user_by_phone
from utils.dusty import dusty_response
from services.twilio_tools import send_sms

manage_bp = Blueprint("manage", __name__)

def get_admin_user():
    return User.query.filter_by(name="Ronnie").first()

@manage_bp.route('/add', methods=['GET', 'POST'])
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

        if assigned_to and assigned_to.phone:
            send_sms(
                assigned_to.phone,
                dusty_response(
                    "assigned",
                    name=assigned_to.name,
                    extra=f"{new_chore.name} (due {new_chore.due_date.strftime('%b %d') if new_chore.due_date else 'someday'})"
                )
            )

        flash('Chore added successfully')
        return redirect(url_for('index'))

    return render_template('add_chore.html', users=users)


@manage_bp.route('/delete/<int:chore_id>', methods=['POST'])
def delete_chore(chore_id):
    user = get_admin_user()
    if not user or not user.is_admin:
        flash("You're not allowed to delete chores", "danger")
        return redirect(url_for('views.index'))

    chore = Chore.query.get_or_404(chore_id)
    db.session.delete(chore)
    db.session.commit()
    flash(f"Deleted chore: {chore.name}", "success")
    return redirect(url_for('views.index'))


@manage_bp.route('/unassign/<int:chore_id>', methods=['POST'])
def unassign_chore(chore_id):
    user = get_admin_user()
    if not user or not user.is_admin:
        flash("Not authorized.", "danger")
        return redirect(url_for('views.index'))

    chore = Chore.query.get_or_404(chore_id)
    chore.assigned_to_id = None
    db.session.commit()
    flash(f"Unassigned chore: {chore.name}", "info")
    return redirect(url_for('views.index'))


@manage_bp.route('/reassign/<int:chore_id>', methods=['POST'])
def reassign_chore(chore_id):
    user = get_admin_user()
    if not user or not user.is_admin:
        flash("Not authorized.", "danger")
        return redirect(url_for('index'))

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
    return redirect(url_for('index'))