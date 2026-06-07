import hashlib
from sqlalchemy import text
from db_v2 import engine


def hash_password_v2(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_user_v2(username, password, role, team_id=None):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users(username, password_hash, role, team_id, is_active)
            VALUES(:username, :password_hash, :role, :team_id, 1)
        """), {
            "username": username,
            "password_hash": hash_password_v2(password),
            "role": role,
            "team_id": team_id
        })


def authenticate_user_v2(username, password):
    with engine.begin() as conn:
        user = conn.execute(text("""
            SELECT u.user_id, u.username, u.password_hash, u.role, u.team_id, t.team_name, u.is_active
            FROM users u
            LEFT JOIN teams t ON t.team_id = u.team_id
            WHERE u.username = :username
        """), {"username": username}).mappings().first()

    if not user or not user["is_active"]:
        return None
    if user["password_hash"] != hash_password_v2(password):
        return None
    return dict(user)


def get_all_users_v2():
    with engine.begin() as conn:
        return conn.execute(text("""
            SELECT u.user_id, u.username, u.role, t.team_name, u.is_active
            FROM users u
            LEFT JOIN teams t ON t.team_id = u.team_id
            ORDER BY u.role, u.username
        """)).mappings().all()
