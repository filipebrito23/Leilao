import bcrypt
from sqlalchemy import text
from db_v5 import engine


def hash_password_v5(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


def verify_password_v5(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8")
    )


def create_user_v5(email, password, role, team_id=None, must_change_password=1):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (
                email,
                password_hash,
                role,
                team_id,
                is_active,
                must_change_password
            )
            VALUES (
                :email,
                :password_hash,
                :role,
                :team_id,
                1,
                :must_change_password
            )
        """), {
            "email": email.strip().lower(),
            "password_hash": hash_password_v5(password),
            "role": role,
            "team_id": team_id,
            "must_change_password": must_change_password
        })


def authenticate_user_v5(email, password):
    with engine.begin() as conn:
        user = conn.execute(text("""
            SELECT
                u.user_id,
                u.email,
                u.password_hash,
                u.role,
                u.team_id,
                t.team_name,
                u.is_active,
                u.must_change_password
            FROM users u
            LEFT JOIN teams t
                ON t.team_id = u.team_id
            WHERE lower(u.email) = :email
        """), {
            "email": email.strip().lower()
        }).mappings().first()

    if not user:
        return None

    if not user["is_active"]:
        return None

    if not verify_password_v5(password, user["password_hash"]):
        return None

    return dict(user)


def change_password_v5(user_id, new_password):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE users
            SET
                password_hash = :password_hash,
                must_change_password = 0
            WHERE user_id = :user_id
        """), {
            "password_hash": hash_password_v5(new_password),
            "user_id": user_id
        })


def get_all_users_v5():
    with engine.begin() as conn:
        return conn.execute(text("""
            SELECT
                u.user_id,
                u.email,
                u.role,
                t.team_name,
                u.is_active,
                u.must_change_password
            FROM users u
            LEFT JOIN teams t
                ON t.team_id = u.team_id
            ORDER BY u.role, u.email
        """)).mappings().all()