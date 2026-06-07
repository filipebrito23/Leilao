from pathlib import Path
import pandas as pd
from sqlalchemy import text
from db_v5 import engine, init_db_v5
from auth_v5 import create_user_v5

POSITION_SHEETS = ["PG", "PGSG", "SG", "SGSF", "SF", "SFPF", "PF", "PFC", "C"]


def import_caps_v5(xlsx_path):
    df = pd.read_excel(xlsx_path, sheet_name="Cap")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns={df.columns[0]: "team_name", df.columns[1]: "cap_limit"})
    df = df.dropna(subset=["team_name"])

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
            else:
                conn.execute(text("""
                    INSERT INTO teams (team_name, cap_limit)
                    VALUES (:team_name, :cap_limit)
                """), {
                    "team_name": team_name,
                    "cap_limit": cap_limit
                })


def import_players_v5(xlsx_path):
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

        conn.execute(text("""
            INSERT INTO player_state (player_id, status, is_renewal)
            SELECT p.player_id, 'OPEN', 0
            FROM players p
            LEFT JOIN player_state ps
                ON ps.player_id = p.player_id
            WHERE ps.player_id IS NULL
        """))


def seed_default_admin_v5():
    with engine.begin() as conn:
        exists = conn.execute(text("""
            SELECT COUNT(*)
            FROM users
            WHERE lower(email) = 'admin@auction.local'
        """)).scalar()

    if not exists:
        create_user_v5(
            "admin@auction.local",
            "admin123",
            "admin",
            None,
            must_change_password=0
        )


def seed_example_team_users_v5():
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


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent
    xlsx_path = base_dir / "Lista.xlsx"

    init_db_v5()
    import_caps_v5(xlsx_path)
    import_players_v5(xlsx_path)
    seed_default_admin_v5()
    seed_example_team_users_v5()

    print("Importação v5 concluída com sucesso.")