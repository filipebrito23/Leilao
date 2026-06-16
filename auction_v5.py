from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from db_v5 import engine

def utc_now_iso_v5():
    return datetime.now(timezone.utc).isoformat()

def log_event_v5(username, action, entity_type, entity_id=None, details=None):
    with engine.begin() as conn:
        conn.execute(text("""
        INSERT INTO audit_log (event_time, username, action, entity_type, entity_id, details)
        VALUES (:event_time, :username, :action, :entity_type, :entity_id, :details)
        """), {
            "event_time": utc_now_iso_v5(),
            "username": username,
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id is not None else None,
            "details": details,
        })

def get_team_cap_status_v5(conn, team_id):
    cap_limit = conn.execute(text("SELECT cap_limit FROM teams WHERE team_id = :team_id"), {"team_id": team_id}).scalar()
    used = conn.execute(text("""
        SELECT COALESCE(SUM(b.amount), 0)
        FROM bids b
        WHERE b.team_id = :team_id
          AND b.is_active = 1
          AND b.is_valid = 1
          AND b.is_renewal = 0
          AND b.deleted_at IS NULL
    """), {"team_id": team_id}).scalar()
    cap_limit = float(cap_limit or 0)
    used = float(used or 0)
    return cap_limit, used, cap_limit - used

def close_expired_bids_v5():
    now = utc_now_iso_v5()
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT player_id
            FROM player_state
            WHERE status = 'OPEN'
              AND expires_at IS NOT NULL
              AND expires_at < :now
        """), {"now": now}).fetchall()
        for row in rows:
            conn.execute(text("UPDATE player_state SET status = 'CLOSED' WHERE player_id = :player_id"), {"player_id": row.player_id})
            conn.execute(text("UPDATE players SET status = 'CLOSED', closed_at = :now WHERE player_id = :player_id"), {"player_id": row.player_id, "now": now})

def submit_bid_v5(player_id, team_id, amount, years, username, user_id, role, forced_team_id=None):
    if role != 'admin' and forced_team_id is not None and team_id != forced_team_id:
        return False, 'Usuário não pode lançar por outro time.'
    if amount is None or float(amount) <= 0:
        return False, 'O valor da proposta deve ser maior que zero.'
    if years is None or int(years) <= 0:
        return False, 'A quantidade de anos deve ser maior que zero.'

    close_expired_bids_v5()
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    expires_at = (now_dt + timedelta(hours=24)).isoformat()

    with engine.begin() as conn:
        player = conn.execute(text("SELECT player_id, owner_team_id, status FROM players WHERE player_id = :player_id"), {"player_id": player_id}).mappings().first()
        if not player:
            return False, 'Jogador não encontrado.'
        if player['status'] != 'OPEN':
            return False, 'Leilão desse jogador já foi fechado.'

        is_renewal = 1 if player['owner_team_id'] == team_id else 0
        _, _, available = get_team_cap_status_v5(conn, team_id)

        current_active = conn.execute(text("""
            SELECT active_bid_id, active_team_id, active_amount
            FROM player_state
            WHERE player_id = :player_id
        """), {"player_id": player_id}).mappings().first()

        released_amount = 0.0
        if current_active and current_active['active_team_id'] == team_id:
            released_amount = float(current_active['active_amount'] or 0)

        current_amount = None
        if current_active and current_active['active_amount'] is not None:
            current_amount = float(current_active['active_amount'])

        amount = float(amount)
        years = int(years)

        if current_amount is not None:
            if is_renewal and amount < current_amount:
                return False, f'Proposta de renovação não pode ser menor que a proposta ativa ({current_amount:,.2f}).'
            if not is_renewal and amount <= current_amount:
                return False, f'Nova proposta deve ser maior que a proposta ativa ({current_amount:,.2f}).'

        effective_available = available + (0 if is_renewal else released_amount)
        if not is_renewal and amount > effective_available:
            return False, f'Cap insuficiente. Disponível: {effective_available:,.2f}'

        if current_active and current_active['active_bid_id']:
            conn.execute(text("UPDATE bids SET is_active = 0 WHERE bid_id = :bid_id"), {"bid_id": current_active['active_bid_id']})

        bid_id = conn.execute(text("""
            INSERT INTO bids (player_id, team_id, amount, years, created_at, is_valid, is_active, is_renewal, created_by_user_id)
            VALUES (:player_id, :team_id, :amount, :years, :created_at, 1, 1, :is_renewal, :created_by_user_id)
            RETURNING bid_id
        """), {
            'player_id': player_id, 'team_id': team_id, 'amount': amount, 'years': years,
            'created_at': now, 'is_renewal': is_renewal, 'created_by_user_id': user_id
        }).scalar()

        payload = dict(player_id=player_id, bid_id=bid_id, team_id=team_id, amount=amount, years=years, active_at=now, expires_at=expires_at, is_renewal=is_renewal)
        exists = conn.execute(text("SELECT COUNT(*) FROM player_state WHERE player_id = :player_id"), {"player_id": player_id}).scalar()
        if exists:
            conn.execute(text("""
                UPDATE player_state
                SET active_bid_id = :bid_id, active_team_id = :team_id, active_amount = :amount, active_years = :years, active_at = :active_at, expires_at = :expires_at, status = 'OPEN', is_renewal = :is_renewal
                WHERE player_id = :player_id
            """), payload)
        else:
            conn.execute(text("""
                INSERT INTO player_state (player_id, active_bid_id, active_team_id, active_amount, active_years, active_at, expires_at, status, is_renewal)
                VALUES (:player_id, :bid_id, :team_id, :amount, :years, :active_at, :expires_at, 'OPEN', :is_renewal)
            """), payload)

        log_event_v5(username, 'SUBMIT_BID', 'player', player_id, f'amount={amount}; years={years}; renewal={is_renewal}')
        return True, 'Proposta registrada com sucesso.'

def update_bid_v5(bid_id, amount, years, username, user_id):
    with engine.begin() as conn:
        row = conn.execute(text("SELECT bid_id, player_id, team_id, is_active, deleted_at FROM bids WHERE bid_id = :bid_id"), {"bid_id": bid_id}).mappings().first()
        if not row or row['deleted_at'] is not None:
            return False, 'Proposta não encontrada.'
        amount = float(amount)
        years = int(years)
        if amount <= 0 or years <= 0:
            return False, 'Valor e anos devem ser maiores que zero.'

        conn.execute(text("""
            UPDATE bids
            SET amount = :amount, years = :years, updated_at = :updated_at, updated_by_user_id = :updated_by_user_id
            WHERE bid_id = :bid_id
        """), {"amount": amount, "years": years, "updated_at": utc_now_iso_v5(), "updated_by_user_id": user_id, "bid_id": bid_id})

        if row['is_active'] == 1:
            conn.execute(text("""
                UPDATE player_state
                SET active_amount = :amount, active_years = :years
                WHERE active_bid_id = :bid_id
            """), {"amount": amount, "years": years, "bid_id": bid_id})

        log_event_v5(username, 'UPDATE_BID', 'bid', bid_id, f'amount={amount}; years={years}')
        return True, 'Proposta atualizada com sucesso.'

def delete_bid_v5(bid_id, username, user_id, reason=None):
    now = utc_now_iso_v5()
    with engine.begin() as conn:
        row = conn.execute(text("SELECT bid_id, is_active, deleted_at FROM bids WHERE bid_id = :bid_id"), {"bid_id": bid_id}).mappings().first()
        if not row or row['deleted_at'] is not None:
            return False, 'Proposta não encontrada.'

        conn.execute(text("""
            UPDATE bids
            SET is_active = 0, is_valid = 0, deleted_at = :deleted_at, delete_reason = :reason, deleted_by_user_id = :deleted_by_user_id
            WHERE bid_id = :bid_id
        """), {"deleted_at": now, "reason": reason, "deleted_by_user_id": user_id, "bid_id": bid_id})

        conn.execute(text("""
            UPDATE player_state
            SET active_bid_id = NULL, active_team_id = NULL, active_amount = NULL, active_years = NULL, active_at = NULL, expires_at = NULL, status = 'OPEN', is_renewal = 0
            WHERE active_bid_id = :bid_id
        """), {"bid_id": bid_id})

        log_event_v5(username, 'DELETE_BID', 'bid', bid_id, reason or 'deleted by admin')
        return True, 'Proposta excluída com sucesso.'

def get_players_with_state_v5(position=None):
    query = """
    SELECT p.player_id, p.player_name, p.position, owner.team_name AS dono, t.team_name AS time_ativo, ps.active_amount AS proposta_ativa, ps.active_years AS anos, ps.active_at, ps.expires_at, ps.status, ps.is_renewal
    FROM players p
    LEFT JOIN teams owner ON owner.team_id = p.owner_team_id
    LEFT JOIN player_state ps ON ps.player_id = p.player_id
    LEFT JOIN teams t ON t.team_id = ps.active_team_id
    """
    params = {}
    if position and position != 'Todas':
        query += " WHERE p.position = :position"
        params['position'] = position
    query += " ORDER BY p.position, p.player_name"
    with engine.begin() as conn:
        return conn.execute(text(query), params).mappings().all()

def get_bid_history_v5(player_id):
    with engine.begin() as conn:
        return conn.execute(text("""
            SELECT b.bid_id, t.team_name, b.amount, b.years, b.created_at, b.updated_at, b.deleted_at, b.delete_reason, b.is_active, b.is_renewal, u.email AS created_by
            FROM bids b
            JOIN teams t ON t.team_id = b.team_id
            LEFT JOIN users u ON u.user_id = b.created_by_user_id
            WHERE b.player_id = :player_id
            ORDER BY b.created_at DESC
        """), {"player_id": player_id}).mappings().all()

def get_all_bids_v5(limit=200):
    with engine.begin() as conn:
        return conn.execute(text("""
            SELECT b.bid_id, p.player_name, p.position, t.team_name, b.amount, b.years, b.created_at, b.updated_at, b.deleted_at, b.delete_reason, b.is_active, b.is_valid, b.is_renewal, u.email AS created_by
            FROM bids b
            JOIN players p ON p.player_id = b.player_id
            JOIN teams t ON t.team_id = b.team_id
            LEFT JOIN users u ON u.user_id = b.created_by_user_id
            ORDER BY b.bid_id DESC
            LIMIT :limit
        """), {"limit": limit}).mappings().all()

def get_team_rows_v5():
    with engine.begin() as conn:
        return conn.execute(text("""
            SELECT t.team_id, t.team_name, t.cap_limit, COALESCE(SUM(CASE WHEN b.is_active = 1 AND b.is_valid = 1 AND b.is_renewal = 0 AND b.deleted_at IS NULL THEN b.amount ELSE 0 END), 0) AS used_cap, t.cap_limit - COALESCE(SUM(CASE WHEN b.is_active = 1 AND b.is_valid = 1 AND b.is_renewal = 0 AND b.deleted_at IS NULL THEN b.amount ELSE 0 END), 0) AS available_cap
            FROM teams t
            LEFT JOIN bids b ON b.team_id = t.team_id
            GROUP BY t.team_id, t.team_name, t.cap_limit
            ORDER BY available_cap DESC
        """)).mappings().all()

def get_audit_rows_v5(limit=200):
    with engine.begin() as conn:
        return conn.execute(text("""
            SELECT event_time, username, action, entity_type, entity_id, details
            FROM audit_log
            ORDER BY audit_id DESC
            LIMIT :limit
        """), {"limit": limit}).mappings().all()
