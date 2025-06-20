# routes/misc.py

from flask import Blueprint, redirect, url_for, flash, render_template
from datetime import timedelta
from models import db, Chore, User
from utils.chores import get_unassigned_chores

misc_bp = Blueprint("misc", __name__)

def get_admin_user():
    return User.query.filter_by(name="Ronnie").first()

@misc_bp.route('/snooze/<int:chore_id>', methods=['POST'])
def snooze_chore(chore_id):
    user = get_admin_user()
    if not user or not user.is_admin:
        flash("Not authorized.", "danger")
        return redirect(url_for('views.index'))

    chore = Chore.query.get_or_404(chore_id)

    if not chore.due_date:
        flash(f"Chore '{chore.name}' has no due date to snooze.", "warning")
        return redirect(url_for('views.index'))

    # Snooze logic
    if chore.recurrence == 'weekly':
        chore.due_date += timedelta(days=7)
    else:
        chore.due_date += timedelta(days=1)

    db.session.commit()
    flash(f"Snoozed chore '{chore.name}' to {chore.due_date.strftime('%Y-%m-%d')}.", "info")
    return redirect(url_for('views.index'))


@misc_bp.route('/unassigned')
def unassigned():
    chores = get_unassigned_chores()
    return render_template('unassigned.html', chores=chores)