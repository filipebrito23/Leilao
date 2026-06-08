from pathlib import Path
import pandas as pd
import streamlit as st
from sqlalchemy import text

from db_v5 import engine, init_db_v5
from auth_v5 import create_user_v5

POSITION_SHEETS = ["PG", "PG_SG", "SG", "SG_SF", "SF", "SF_PF", "PF", "PF_C", "C"]


def is_production_v5():
    app_cfg = st.secrets.get("app", {})
    return str(app_cfg.get("environment", "development")).lower() == "production"


def import_caps_v5(xlsx_path):
    df = pd.read_excel(xlsx_path, sheet_name="Cap")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={df.columns[0]: "team_name", df.columns[1]: "cap_limit"})
    df = df.dropna(subset=["team_name"])

    inserted = 0
    updated = 0

    with engine.begin() as conn:
        for _, row in df.iterrows():
            team_name = str(row["team_name"]).strip()
            cap_limit = float(row["cap_limit"])

            existing_team_id = conn.execute(text("""
                SELECT team_id
                FROM teams
                WHERE lower(team_name) = lower(:team_name)
            """), {
                "team_name": team_name
            }).scalar()

            if existing_team_id:
                conn.execute(text("""
                    UPDATE teams
                    SET team_name = :team_name,
                        cap_limit = :cap_limit
                    WHERE team_id = :team_id
                """), {
                    "team_name": team_name,
                    "cap_limit": cap_limit,
                    "team_id": existing_team_id
                })
                updated += 1
            else:
                conn.execute(text("""
                    INSERT INTO teams (team_name, cap_limit)
                    VALUES (:team_name, :cap_limit)
                """), {
                    "team_name": team_name,
                    "cap_limit": cap_limit
                })
                inserted += 1

    return {"inserted": inserted, "updated": updated}


def import_players_v5(xlsx_path):
    xl = pd.ExcelFile(xlsx_path)

    inserted = 0
    updated = 0

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
                    owner_team_id = conn.execute(text("""
                        SELECT team_id
                        FROM teams
                        WHERE lower(team_name) = lower(:team_name)
                    """), {
                        "team_name": owner_name
                    }).scalar()

                existing_player_id = conn.execute(text("""
                    SELECT player_id
                    FROM players
                    WHERE lower(player_name) = lower(:player_name)
                      AND position = :position
                """), {
                    "player_name": player_name,
                    "position": sheet
                }).scalar()

                if existing_player_id:
                    conn.execute(text("""
                        UPDATE players
                        SET owner_team_id = :owner_team_id
                        WHERE player_id = :player_id
                    """), {
                        "owner_team_id": owner_team_id,
                        "player_id": existing_player_id
                    })
                    updated += 1
                else:
                    conn.execute(text("""
                        INSERT INTO players (
                            player_name,
                            position,
                            owner_team_id,
                            status
                        )
                        VALUES (
                            :player_name,
                            :position,
                            :owner_team_id,
                            'OPEN'
                        )
                    """), {
                        "player_name": player_name,
                        "position": sheet,
                        "owner_team_id": owner_team_id
                    })
                    inserted += 1

        conn.execute(text("""
            INSERT INTO player_state (player_id, status, is_renewal)
            SELECT p.player_id, 'OPEN', 0
            FROM players p
            LEFT JOIN player_state ps
                ON ps.player_id = p.player_id
            WHERE ps.player_id IS NULL
        """))

    return {"inserted": inserted, "updated": updated}


def seed_default_admin_v5():
    app_cfg = st.secrets.get("app", {})
    admin_email = app_cfg.get("admin_email", "admin@auction.local")
    admin_password = app_cfg.get("admin_password", "trocar_essa_senha")

    with engine.begin() as conn:
        exists = conn.execute(text("""
            SELECT COUNT(*)
            FROM users
            WHERE lower(email) = lower(:email)
        """), {
            "email": admin_email
        }).scalar()

    if not exists:
        create_user_v5(
            admin_email,
            admin_password,
            "admin",
            None,
            must_change_password=0
        )
        return True

    return False


def seed_example_team_users_v5():
    if is_production_v5():
        return 0

    created = 0

    with engine.begin() as conn:
        teams = conn.execute(text("""
            SELECT team_id, team_name
            FROM teams
            ORDER BY team_name
        """)).fetchall()

    for team_id, team_name in teams:
        email = f"{str(team_name).strip().lower().replace(' ', '_')}@auction.local"

        with engine.begin() as conn:
            exists = conn.execute(text("""
                SELECT COUNT(*)
                FROM users
                WHERE lower(email) = :email
            """), {
                "email": email
            }).scalar()

        if not exists:
            create_user_v5(
                email,
                "123456",
                "team",
                team_id,
                must_change_password=1
            )
            created += 1

    return created


def run_import_v5(xlsx_path):
    init_db_v5()

    cap_result = import_caps_v5(xlsx_path)
    player_result = import_players_v5(xlsx_path)
    admin_created = seed_default_admin_v5()
    demo_users_created = seed_example_team_users_v5()

    return {
        "caps": cap_result,
        "players": player_result,
        "admin_created": admin_created,
        "demo_users_created": demo_users_created
    }


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent
    xlsx_path = base_dir / "Lista.xlsx"

    if not xlsx_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {xlsx_path}")

    result = run_import_v5(xlsx_path)
    print(result)