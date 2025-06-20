import os
from datetime import datetime
from models import  User



# -------------------------------
# User Seeding from Environment Variables
# -------------------------------

def seed_users_from_env(session):
    from sqlalchemy.exc import IntegrityError

    print("🔧 Seeding users from environment variables...")
    users_added = 0
    for key, value in os.environ.items():
        if key.startswith("USER_"):
            name = key.replace("USER_", "").strip()
            phone = value.strip()

            existing = session.query(User).filter_by(phone=phone).first()
            if existing:
                print(f"⚠️  Skipping existing user: {name} ({phone})")
                continue

            is_admin = name.lower() in ["ronnie", "becky"]  # ← mark admins
            user = User(name=name, phone=phone, is_admin=is_admin)
            session.add(user)
            users_added += 1

    try:
        session.commit()
        print(f"✅ Seeded {users_added} user(s).")
    except IntegrityError as e:
        session.rollback()
        print(f"❌ Integrity error during seeding: {e}")










# -------------------------------
# User Utilities
# -------------------------------

def reduce_fatigue(user):
    """Reduce fatigue gradually based on last_seen time."""
    if not user.last_seen:
        return
    minutes_since = (datetime.utcnow() - user.last_seen).total_seconds() / 60
    if minutes_since >= 10:  # Cooldown every 10 minutes
        user.fatigue_level = max(0, user.fatigue_level - 1)

def get_user_by_name(name: str) -> User | None:
    """Retrieve a user by their name (case-insensitive)."""
    return User.query.filter(User.name.ilike(name.strip())).first()

def get_user_by_phone(phone) :
    """Retrieve a user by their phone number."""
    
    return User.query.filter_by(phone=phone).first()

