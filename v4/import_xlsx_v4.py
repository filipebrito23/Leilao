from pathlib import Path
import pandas as pd
from sqlalchemy import text
from db_v4 import engine, init_db_v4
from auth_v4 import create_user_v4

POSITION_SHEETS = ["PG", "PG_SG", "SG", "SG_SF", "SF", "SF_PF", "PF", "PF_C", "C"]


def import_caps_v4(xlsx_path):
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


def import_players_v4(xlsx_path):
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
                    owner_team_id = conn.execute(text("SELECT team_id FROM teams WHERE team_name = :name"), {"name": owner_name}).scalar()
                conn.execute(text("""
                    INSERT OR IGNORE INTO players(player_name, position, owner_team_id, status)
                    VALUES(:player_name, :position, :owner_team_id, 'OPEN')
                """), {"player_name": player_name, "position": sheet, "owner_team_id": owner_team_id})
        conn.execute(text("""
            INSERT OR IGNORE INTO player_state(player_id, status, is_renewal)
            SELECT player_id, 'OPEN', 0 FROM players
        """))


def seed_default_admin_v4():
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT COUNT(*) FROM users WHERE lower(email) = 'admin@auction.local' ")).scalar()
    if not exists:
        create_user_v4("admin@auction.local", "admin123", "admin", None, must_change_password=0)


def seed_example_team_users_v4():
    with engine.begin() as conn:
        teams = conn.execute(text("SELECT team_id, team_name FROM teams ORDER BY team_name")).fetchall()
    for team_id, team_name in teams:
        email = f"{str(team_name).strip().lower().replace(' ', '_')}@auction.local"
        with engine.begin() as conn:
            exists = conn.execute(text("SELECT COUNT(*) FROM users WHERE lower(email)=:email"), {"email": email}).scalar()
        if not exists:
            create_user_v4(email, "123456", "team", team_id, must_change_password=1)


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent
    xlsx_path = base_dir / "Lista.xlsx"
    init_db_v4()
    import_caps_v4(xlsx_path)
    import_players_v4(xlsx_path)
    seed_default_admin_v4()
    seed_example_team_users_v4()
    print("Importação v4 concluída com sucesso.")
