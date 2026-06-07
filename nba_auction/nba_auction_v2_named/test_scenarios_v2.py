from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from db_v2 import engine, init_db_v2
from auction_v2 import submit_bid_v2, get_bid_history_v2, get_players_with_state_v2, close_expired_bids_v2, admin_delete_bid_v2


def get_first_player(owner_required=False):
    rows = get_players_with_state_v2("Todas")
    for r in rows:
        if owner_required and r["dono"]:
            return r
        if not owner_required:
            return r
    return None


def get_team(conn, team_name=None, not_name=None):
    if team_name:
        return conn.execute(text("SELECT team_id, team_name FROM teams WHERE team_name = :name LIMIT 1"), {"name": team_name}).fetchone()
    if not_name:
        return conn.execute(text("SELECT team_id, team_name FROM teams WHERE team_name <> :name LIMIT 1"), {"name": not_name}).fetchone()
    return conn.execute(text("SELECT team_id, team_name FROM teams LIMIT 1")).fetchone()


def main():
    init_db_v2()
    results = []

    with engine.begin() as conn:
        admin = conn.execute(text("SELECT user_id, username FROM users WHERE username='admin' LIMIT 1")).fetchone()

        p1 = get_first_player(owner_required=False)
        team1 = get_team(conn)
        ok, msg = submit_bid_v2(p1['player_id'], team1[0], 1000000, 2, admin[1], admin[0], 'admin')
        results.append(("lance normal", ok, msg))

        p2 = get_first_player(owner_required=True)
        owner_team = get_team(conn, team_name=p2['dono'])
        ok, msg = submit_bid_v2(p2['player_id'], owner_team[0], 2000000, 3, admin[1], admin[0], 'admin')
        results.append(("renovação ativa", ok, msg))

        other_team = get_team(conn, not_name=team1[1])
        ok, msg = submit_bid_v2(p1['player_id'], other_team[0], 1500000, 3, admin[1], admin[0], 'admin')
        results.append(("troca de liderança", ok, msg))

        hist = get_bid_history_v2(p1['player_id'])
        bid_to_delete = hist[0]['bid_id'] if hist else None
        if bid_to_delete:
            admin_delete_bid_v2(bid_to_delete, admin[1])
            results.append(("exclusão de lance pelo admin", True, f"bid {bid_to_delete} excluído"))
        else:
            results.append(("exclusão de lance pelo admin", False, "nenhum bid para excluir"))

        if p2:
            conn.execute(text("UPDATE player_state SET expires_at = :dt WHERE player_id = :player_id"), {
                "dt": (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(),
                "player_id": p2['player_id']
            })
            close_expired_bids_v2()
            status = conn.execute(text("SELECT status FROM player_state WHERE player_id = :player_id"), {"player_id": p2['player_id']}).scalar()
            results.append(("fechamento após 24h", status == 'CLOSED', f"status={status}"))

        ok, msg = submit_bid_v2(p1['player_id'], other_team[0], 1800000, 2, 'fake_team_user', 9999, 'team', team1[0])
        results.append(("bloqueio de usuário comum tentando lançar por outro time", ok is False, msg))

    print("CENÁRIOS DE TESTE V2")
    for name, ok, msg in results:
        print(f"- {name}: {'OK' if ok else 'FALHOU'} | {msg}")


if __name__ == '__main__':
    main()
