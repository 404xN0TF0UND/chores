
# routes/history.py

from flask import Blueprint, redirect, url_for, flash, render_template, request
from datetime import datetime
from models import db, Chore, ChoreHistory, User, ChoreStats
from utils.dusty import dusty_response
from services.twilio_tools import send_sms

history_bp = Blueprint("history", __name__)

def get_admin_user():
    return User.query.filter_by(name="Ronnie").first()

def notify_admins(chore, user):
    admins = User.query.filter_by(is_admin=True).all()
    message = f"{user.name} just completed the chore: {chore.name} (due {chore.due_date})"
    for admin in admins:
        if admin.phone:
            send_sms(admin.phone, f"[Dusty Alert 🚨] {message}")


@history_bp.route('/complete/<int:chore_id>')
def complete_chore(chore_id):
    chore = Chore.query.get_or_404(chore_id)
    if not chore.completed:
        chore.completed = True
        chore.completed_at = datetime.utcnow()
        db.session.add(chore)

        # Track stats
        if chore.assigned_to:
            stat = ChoreStats.query.filter_by(user_id=chore.assigned_to.id, chore_name=chore.name).first()
            if stat:
                stat.times_completed += 1
            else:
                stat = ChoreStats(user_id=chore.assigned_to.id, chore_name=chore.name, times_completed=1)
            db.session.add(stat)

            # Add to history
            history = ChoreHistory(chore_name=chore.name, user_id=chore.assigned_to.id, completed=True)
            db.session.add(history)

            # Update user stats
            chore.assigned_to.total_chores_completed += 1
            favorite = (
                ChoreStats.query
                .filter_by(user_id=chore.assigned_to.id)
                .order_by(ChoreStats.times_completed.desc())
                .first()
            )
            if favorite:
                chore.assigned_to.favorite_chore = favorite.chore_name

            notify_admins(chore, chore.assigned_to)

        db.session.commit()
        flash(f"Chore '{chore.name}' marked as complete.", 'success')
    else:
        flash(f"Chore '{chore.name}' was already completed.", 'info')
    return redirect(url_for('main.index'))


@history_bp.route("/chore-history")
def chore_history():
    user_id = request.args.get("user_id", type=int)
    selected_user = request.args.get("user_id", type=int)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    query = ChoreHistory.query
    if user_id:
        query = query.filter(ChoreHistory.user_id == user_id)
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(ChoreHistory.completed_at >= start_dt)
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            query = query.filter(ChoreHistory.completed_at <= end_dt)
        except ValueError:
            pass

    history = query.order_by(ChoreHistory.completed_at.desc()).all()
    users = User.query.order_by(User.name).all()
    return render_template("chore_history.html", history=history, users=users,
                           selected_user=selected_user, start_date=start_date, end_date=end_date)

