from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from db_v2 import engine


def log_event_v2(username, action, entity_type, entity_id=None, details=None):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO audit_log(event_time, username, action, entity_type, entity_id, details)
            VALUES(:event_time, :username, :action, :entity_type, :entity_id, :details)
        """), {
            "event_time": datetime.now(timezone.utc).isoformat(),
            "username": username,
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id is not None else None,
            "details": details
        })


def get_team_cap_status_v2(conn, team_id):
    cap_limit = conn.execute(text("SELECT cap_limit FROM teams WHERE team_id = :team_id"), {"team_id": team_id}).scalar()
    used = conn.execute(text("""
        SELECT COALESCE(SUM(b.amount), 0)
        FROM bids b
        WHERE b.team_id = :team_id
          AND b.is_active = 1
          AND b.is_valid = 1
          AND b.is_renewal = 0
    """), {"team_id": team_id}).scalar()
    return float(cap_limit or 0), float(used or 0), float((cap_limit or 0) - (used or 0))


def close_expired_bids_v2():
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT player_id
            FROM player_state
            WHERE status = 'OPEN'
              AND expires_at IS NOT NULL
              AND expires_at < :now
        """), {"now": now.isoformat()}).fetchall()
        for row in rows:
            conn.execute(text("UPDATE player_state SET status = 'CLOSED' WHERE player_id = :player_id"), {"player_id": row.player_id})
            conn.execute(text("UPDATE players SET status = 'CLOSED', closed_at = :now WHERE player_id = :player_id"), {"player_id": row.player_id, "now": now.isoformat()})


def submit_bid_v2(player_id, team_id, amount, years, username, user_id, role, forced_team_id=None):
    if role != "admin" and forced_team_id is not None and team_id != forced_team_id:
        return False, "Usuário não pode lançar por outro time."

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=24)

    with engine.begin() as conn:
        player = conn.execute(text("""
            SELECT p.player_id, p.owner_team_id, p.status, p.player_name
            FROM players p
            WHERE p.player_id = :player_id
        """), {"player_id": player_id}).mappings().first()

        if not player:
            return False, "Jogador não encontrado."
        if player["status"] != "OPEN":
            return False, "Leilão desse jogador já foi fechado."

        is_renewal = 1 if player["owner_team_id"] == team_id else 0
        _, _, available = get_team_cap_status_v2(conn, team_id)

        current_active = conn.execute(text("""
            SELECT active_bid_id, active_team_id, active_amount
            FROM player_state
            WHERE player_id = :player_id
        """), {"player_id": player_id}).mappings().first()

        released_amount = 0
        if current_active and current_active["active_team_id"] == team_id:
            released_amount = float(current_active["active_amount"] or 0)

        effective_available = available + (0 if is_renewal else released_amount)
        if not is_renewal and amount > effective_available:
            return False, f"Cap insuficiente. Disponível: {effective_available:,.2f}"

        if current_active and current_active["active_bid_id"]:
            conn.execute(text("UPDATE bids SET is_active = 0 WHERE bid_id = :bid_id"), {"bid_id": current_active["active_bid_id"]})

        result = conn.execute(text("""
            INSERT INTO bids(player_id, team_id, amount, years, created_at, is_valid, is_active, is_renewal, created_by_user_id)
            VALUES(:player_id, :team_id, :amount, :years, :created_at, 1, 1, :is_renewal, :created_by_user_id)
        """), {
            "player_id": player_id,
            "team_id": team_id,
            "amount": amount,
            "years": years,
            "created_at": now.isoformat(),
            "is_renewal": is_renewal,
            "created_by_user_id": user_id
        })
        bid_id = result.lastrowid

        conn.execute(text("""
            INSERT INTO player_state(player_id, active_bid_id, active_team_id, active_amount, active_years, active_at, expires_at, status, is_renewal)
            VALUES(:player_id, :bid_id, :team_id, :amount, :years, :active_at, :expires_at, 'OPEN', :is_renewal)
            ON CONFLICT(player_id) DO UPDATE SET
                active_bid_id = excluded.active_bid_id,
                active_team_id = excluded.active_team_id,
                active_amount = excluded.active_amount,
                active_years = excluded.active_years,
                active_at = excluded.active_at,
                expires_at = excluded.expires_at,
                status = 'OPEN',
                is_renewal = excluded.is_renewal
        """), {
            "player_id": player_id,
            "bid_id": bid_id,
            "team_id": team_id,
            "amount": amount,
            "years": years,
            "active_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "is_renewal": is_renewal
        })

    log_event_v2(username, "SUBMIT_BID", "player", player_id, f"amount={amount}; years={years}; renewal={is_renewal}")
    return True, "Proposta registrada com sucesso."


def get_players_with_state_v2(position=None):
    query = """
    SELECT
        p.player_id,
        p.player_name,
        p.position,
        owner.team_name AS dono,
        t.team_name AS time_ativo,
        ps.active_amount AS proposta_ativa,
        ps.active_years AS anos,
        ps.active_at,
        ps.expires_at,
        ps.status,
        ps.is_renewal
    FROM players p
    LEFT JOIN teams owner ON owner.team_id = p.owner_team_id
    LEFT JOIN player_state ps ON ps.player_id = p.player_id
    LEFT JOIN teams t ON t.team_id = ps.active_team_id
    """
    params = {}
    if position and position != "Todas":
        query += " WHERE p.position = :position"
        params["position"] = position
    query += " ORDER BY p.position, p.player_name"
    with engine.begin() as conn:
        return conn.execute(text(query), params).mappings().all()


def get_bid_history_v2(player_id):
    with engine.begin() as conn:
        return conn.execute(text("""
            SELECT b.bid_id, t.team_name, b.amount, b.years, b.created_at, b.is_active, b.is_renewal, u.username AS created_by
            FROM bids b
            JOIN teams t ON t.team_id = b.team_id
            LEFT JOIN users u ON u.user_id = b.created_by_user_id
            WHERE b.player_id = :player_id
            ORDER BY b.created_at DESC
        """), {"player_id": player_id}).mappings().all()


def get_team_rows_v2():
    with engine.begin() as conn:
        return conn.execute(text("""
            SELECT t.team_id, t.team_name, t.cap_limit,
                   COALESCE(SUM(CASE WHEN b.is_active = 1 AND b.is_valid = 1 AND b.is_renewal = 0 THEN b.amount ELSE 0 END), 0) AS used_cap,
                   t.cap_limit - COALESCE(SUM(CASE WHEN b.is_active = 1 AND b.is_valid = 1 AND b.is_renewal = 0 THEN b.amount ELSE 0 END), 0) AS available_cap
            FROM teams t
            LEFT JOIN bids b ON b.team_id = t.team_id
            GROUP BY t.team_id, t.team_name, t.cap_limit
            ORDER BY available_cap DESC
        """)).mappings().all()


def get_audit_rows_v2(limit=200):
    with engine.begin() as conn:
        return conn.execute(text("SELECT event_time, username, action, entity_type, entity_id, details FROM audit_log ORDER BY audit_id DESC LIMIT :limit"), {"limit": limit}).mappings().all()


def admin_add_player_v2(player_name, position, owner_team_id, username):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO players(player_name, position, owner_team_id, status) VALUES(:player_name, :position, :owner_team_id, 'OPEN')"), {"player_name": player_name, "position": position, "owner_team_id": owner_team_id})
        player_id = conn.execute(text("SELECT player_id FROM players WHERE player_name = :player_name AND position = :position"), {"player_name": player_name, "position": position}).scalar()
        conn.execute(text("INSERT OR IGNORE INTO player_state(player_id, status, is_renewal) VALUES(:player_id, 'OPEN', 0)"), {"player_id": player_id})
    log_event_v2(username, "ADD_PLAYER", "player", player_id, f"name={player_name}; position={position}")


def admin_delete_player_v2(player_id, username):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM player_state WHERE player_id = :player_id"), {"player_id": player_id})
        conn.execute(text("DELETE FROM bids WHERE player_id = :player_id"), {"player_id": player_id})
        conn.execute(text("DELETE FROM players WHERE player_id = :player_id"), {"player_id": player_id})
    log_event_v2(username, "DELETE_PLAYER", "player", player_id, None)


def admin_reopen_player_v2(player_id, username):
    with engine.begin() as conn:
        conn.execute(text("UPDATE players SET status = 'OPEN', closed_at = NULL WHERE player_id = :player_id"), {"player_id": player_id})
        conn.execute(text("UPDATE player_state SET status = 'OPEN' WHERE player_id = :player_id"), {"player_id": player_id})
    log_event_v2(username, "REOPEN_PLAYER", "player", player_id, None)


def admin_close_player_v2(player_id, username):
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(text("UPDATE players SET status = 'CLOSED', closed_at = :now WHERE player_id = :player_id"), {"player_id": player_id, "now": now})
        conn.execute(text("UPDATE player_state SET status = 'CLOSED' WHERE player_id = :player_id"), {"player_id": player_id})
    log_event_v2(username, "CLOSE_PLAYER", "player", player_id, None)


def admin_delete_bid_v2(bid_id, username):
    with engine.begin() as conn:
        bid = conn.execute(text("SELECT player_id FROM bids WHERE bid_id = :bid_id"), {"bid_id": bid_id}).mappings().first()
        if not bid:
            return
        player_id = bid["player_id"]
        conn.execute(text("DELETE FROM bids WHERE bid_id = :bid_id"), {"bid_id": bid_id})
        latest = conn.execute(text("SELECT bid_id, team_id, amount, years, created_at, is_renewal FROM bids WHERE player_id = :player_id ORDER BY created_at DESC LIMIT 1"), {"player_id": player_id}).mappings().first()
        conn.execute(text("UPDATE bids SET is_active = 0 WHERE player_id = :player_id"), {"player_id": player_id})
        if latest:
            conn.execute(text("UPDATE bids SET is_active = 1 WHERE bid_id = :bid_id"), {"bid_id": latest["bid_id"]})
            conn.execute(text("""
                UPDATE player_state SET active_bid_id = :bid_id, active_team_id = :team_id, active_amount = :amount,
                active_years = :years, active_at = :active_at, expires_at = :expires_at, status = 'OPEN', is_renewal = :is_renewal
                WHERE player_id = :player_id
            """), {
                "bid_id": latest["bid_id"], "team_id": latest["team_id"], "amount": latest["amount"],
                "years": latest["years"], "active_at": latest["created_at"],
                "expires_at": (datetime.fromisoformat(latest["created_at"]) + timedelta(hours=24)).isoformat(),
                "player_id": player_id, "is_renewal": latest["is_renewal"]
            })
        else:
            conn.execute(text("""
                UPDATE player_state SET active_bid_id = NULL, active_team_id = NULL, active_amount = NULL,
                active_years = NULL, active_at = NULL, expires_at = NULL, status = 'OPEN', is_renewal = 0
                WHERE player_id = :player_id
            """), {"player_id": player_id})
    log_event_v2(username, "DELETE_BID", "bid", bid_id, None)
