from datetime import datetime, timedelta
from models import Chore, User, ChoreHistory, db
from sqlalchemy.orm import joinedload

# -------------------------------
# Chore Utilities
# -------------------------------

def get_assigned_chores(user: User) -> list[Chore]:
    """Return list of incomplete chores assigned to user, ordered by due date."""
    return Chore.query.filter_by(assigned_to_id=user.id, completed=False).order_by(Chore.due_date).all()

def get_completed_chores(user: User) -> list[Chore]:
    """Return list of completed chores assigned to user, most recent first."""
    return Chore.query.filter_by(assigned_to_id=user.id, completed=True).order_by(Chore.completed_at.desc()).all()

def get_unassigned_chores(limit=None):
    query = Chore.query.filter_by(assigned_to_id=None).order_by(Chore.due_date.asc())
    if limit:
        query = query.limit(limit)
        return query.all()

def get_chore_history(user=None):
    query = ChoreHistory.query.order_by(ChoreHistory.completed_at.desc())
    if user:
        query = query.filter_by(completed_by_id=user.id)
    return query.all()

def complete_chore_by_name(chore_name, user):
    if not chore_name:
        return None
    chore = Chore.query.filter(
        Chore.assigned_to_id == user.id,
        Chore.name.ilike(f"%{chore_name.strip()}%"),
        Chore.completed == False
    ).first()
    if chore:
        chore.completed = True
        chore.completed_at = datetime.utcnow()
        db.session.commit()
        return chore
    return None


        
def get_upcoming_chores(user, days=3):
    now = datetime.now()
    upcoming = now + timedelta(days=days)
    return Chore.query.filter(
        Chore.assigned_to_id == user.id,
        Chore.due_date != None,
        Chore.completed == False,
        Chore.due_date <= upcoming
    ).order_by(Chore.due_date).all()


def list_user_chores(user, limit=5):
    chores = Chore.query.filter_by(assigned_to_id=user.id, completed=False)\
                .order_by(Chore.due_date.asc().nullslast())\
                .limit(limit).all()
    print(f"[DEBUG] Inside list_user_chores: Found {chores}")
    return chores

def get_due_chores_message(session) -> str:
    """
    Retrieve all chores due today or overdue, format Dusty-style report.
    """
    today = datetime.utcnow().date()
    chores = (
        session.query(Chore)
        .options(joinedload(Chore.assigned_to))
        .filter(Chore.completed == False, Chore.due_date <= today)
        .all()
    )

    if not chores:
        return "[Dusty 🤖] Shockingly, there are no chores due today. Either you're efficient or lying."

    lines = ["[Dusty 🤖] Daily shame report:"]
    for chore in chores:
        name = chore.assigned_to.name if chore.assigned_to else "Unknown"
        due_str = chore.due_date.strftime("%Y-%m-%d") if chore.due_date else "No due date"
        lines.append(f"- {chore.description} (assigned to {name}, due {due_str})")

    return "\n".join(lines)
