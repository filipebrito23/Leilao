from pathlib import Path
import pandas as pd
from sqlalchemy import text
from db import engine, init_db
from auth import create_user

POSITION_SHEETS = ["PG", "PGSG", "SG", "SGSF", "SF", "SFPF", "PF", "PFC", "C"]


def import_caps(xlsx_path):
    df = pd.read_excel(xlsx_path, sheet_name="Cap")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={df.columns[0]: "team_name", df.columns[1]: "cap_limit"})
    df = df.dropna(subset=["team_name"])

    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(text("""
                INSERT OR REPLACE INTO teams(team_id, team_name, cap_limit)
                VALUES(
                    COALESCE((SELECT team_id FROM teams WHERE team_name = :team_name), NULL),
                    :team_name,
                    :cap_limit
                )
            """), {"team_name": str(row["team_name"]).strip(), "cap_limit": float(row["cap_limit"])})


def import_players(xlsx_path):
    xl = pd.ExcelFile(xlsx_path)

    with engine.begin() as conn:
        for sheet in POSITION_SHEETS:
            if sheet not in xl.sheet_names:
                continue

            df = pd.read_excel(xlsx_path, sheet_name=sheet)
            df.columns = [str(c).strip().upper() for c in df.columns]

            if "JOGADOR" not in df.columns:
                continue

            for _, row in df.iterrows():
                player_name = str(row.get("JOGADOR", "")).strip()
                if not player_name or player_name.lower() == "nan":
                    continue

                owner_name = str(row.get("DONO", "")).strip()
                owner_team_id = None

                if owner_name and owner_name.lower() != "nan":
                    owner_team_id = conn.execute(
                        text("SELECT team_id FROM teams WHERE team_name = :name"),
                        {"name": owner_name}
                    ).scalar()

                conn.execute(text("""
                    INSERT OR IGNORE INTO players(player_name, position, owner_team_id, status)
                    VALUES(:player_name, :position, :owner_team_id, 'OPEN')
                """), {
                    "player_name": player_name,
                    "position": sheet,
                    "owner_team_id": owner_team_id
                })

        conn.execute(text("""
            INSERT OR IGNORE INTO player_state(player_id, status, is_renewal)
            SELECT player_id, 'OPEN', 0 FROM players
        """))


def seed_default_admin():
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT COUNT(*) FROM users WHERE username = 'admin' ")).scalar()
    if not exists:
        create_user("admin", "admin123", "admin", None)


def seed_team_users():
    with engine.begin() as conn:
        teams = conn.execute(text("SELECT team_id, team_name FROM teams ORDER BY team_name")).fetchall()
        existing = {row[0] for row in conn.execute(text("SELECT team_id FROM users WHERE team_id IS NOT NULL")).fetchall()}

    for team_id, team_name in teams:
        if team_id in existing:
            continue
        username = str(team_name).strip().lower().replace(" ", "_")
        create_user(username, "123456", "team", team_id)


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent
    xlsx_path = base_dir / "Lista.xlsx"
    init_db()
    import_caps(xlsx_path)
    import_players(xlsx_path)
    seed_default_admin()
    seed_team_users()
