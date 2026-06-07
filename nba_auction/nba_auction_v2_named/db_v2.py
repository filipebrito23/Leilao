from pathlib import Path
import os
from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "auction_v2.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")
engine = create_engine(DATABASE_URL, future=True)


def init_db_v2():
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS teams (
            team_id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT UNIQUE NOT NULL,
            cap_limit REAL NOT NULL
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            team_id INTEGER NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(team_id) REFERENCES teams(team_id)
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS players (
            player_id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT NOT NULL,
            position TEXT NOT NULL,
            owner_team_id INTEGER NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            closed_at TEXT NULL,
            UNIQUE(player_name, position),
            FOREIGN KEY(owner_team_id) REFERENCES teams(team_id)
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS bids (
            bid_id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            years INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            is_valid INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_renewal INTEGER NOT NULL DEFAULT 0,
            invalid_reason TEXT NULL,
            created_by_user_id INTEGER NULL,
            FOREIGN KEY(player_id) REFERENCES players(player_id),
            FOREIGN KEY(team_id) REFERENCES teams(team_id),
            FOREIGN KEY(created_by_user_id) REFERENCES users(user_id)
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS player_state (
            player_id INTEGER PRIMARY KEY,
            active_bid_id INTEGER NULL,
            active_team_id INTEGER NULL,
            active_amount REAL NULL,
            active_years INTEGER NULL,
            active_at TEXT NULL,
            expires_at TEXT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            is_renewal INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(player_id) REFERENCES players(player_id),
            FOREIGN KEY(active_bid_id) REFERENCES bids(bid_id),
            FOREIGN KEY(active_team_id) REFERENCES teams(team_id)
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS audit_log (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time TEXT NOT NULL,
            username TEXT NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NULL,
            details TEXT NULL
        )
        """))
