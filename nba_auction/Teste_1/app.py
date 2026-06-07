from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from sqlalchemy import text
from streamlit_autorefresh import st_autorefresh
from db import engine, init_db
from auth import authenticate_user, get_all_users, create_user
from auction import (
    close_expired_bids,
    submit_bid,
    get_players_with_state,
    get_bid_history,
    get_team_rows,
    get_audit_rows,
    admin_add_player,
    admin_delete_player,
    admin_reopen_player,
    admin_close_player,
    admin_delete_bid,
)

POSITIONS = ["Todas", "PG", "PG_SG", "SG", "SG_SF", "SF", "SF_PF", "PF", "PF_C", "C"]

st.set_page_config(page_title="Leilão NBA Fantasy v2", layout="wide")
init_db()
close_expired_bids()

if "user" not in st.session_state:
    st.session_state.user = None


def logout():
    st.session_state.user = None
    st.rerun()


def format_remaining(expires_at):
    if not expires_at:
        return "-"
    try:
        exp = datetime.fromisoformat(expires_at)
        now = datetime.now(timezone.utc)
        delta = exp - now
        if delta.total_seconds() <= 0:
            return "Encerrado"
        total = int(delta.total_seconds())
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    except Exception:
        return "-"


if not st.session_state.user:
    st.title("Leilão NBA Fantasy v2")
    st.subheader("Login")
    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
        if submitted:
            user = authenticate_user(username, password)
            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    st.info("Usuário admin padrão: admin / admin123")
    st.stop()

user = st.session_state.user
st.sidebar.success(f"Logado como: {user['username']} ({user['role']})")
if user.get("team_name"):
    st.sidebar.write(f"Time vinculado: {user['team_name']}")
st.sidebar.button("Sair", on_click=logout)

st_autorefresh(interval=20000, key="auction_refresh")

st.title("Leilão NBA Fantasy v2")

main_tab, bid_tab, cap_tab, admin_tab = st.tabs(["Propostas", "Nova proposta", "Cap", "Admin"])

with main_tab:
    position = st.selectbox("Posição", POSITIONS)
    players = pd.DataFrame(get_players_with_state(position))
    if not players.empty:
        players["tempo_restante"] = players["expires_at"].apply(format_remaining)
        players["tipo"] = players["is_renewal"].apply(lambda x: "Renovação" if x == 1 else "Oferta")
        st.dataframe(players[["player_id", "player_name", "position", "dono", "time_ativo", "proposta_ativa", "anos", "active_at", "expires_at", "tempo_restante", "tipo", "status"]], use_container_width=True, hide_index=True)

        selected_player = st.selectbox(
            "Ver histórico do jogador",
            players["player_id"].tolist(),
            format_func=lambda pid: players.loc[players["player_id"] == pid, "player_name"].iloc[0]
        )
        history = pd.DataFrame(get_bid_history(selected_player))
        st.markdown("### Histórico do jogador")
        if not history.empty:
            history["tipo"] = history["is_renewal"].apply(lambda x: "Renovação" if x == 1 else "Oferta")
            history["ativa"] = history["is_active"].apply(lambda x: "Sim" if x == 1 else "Não")
            st.dataframe(history[["bid_id", "team_name", "amount", "years", "created_at", "tipo", "ativa", "created_by"]], use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma proposta para este jogador ainda.")
    else:
        st.info("Nenhum jogador encontrado.")

with bid_tab:
    players = pd.DataFrame(get_players_with_state("Todas"))
    open_players = players[players["status"] == "OPEN"] if not players.empty else pd.DataFrame()
    with engine.begin() as conn:
        teams = conn.execute(text("SELECT team_id, team_name FROM teams ORDER BY team_name")).fetchall()
    team_map = {name: tid for tid, name in teams}

    with st.form("bid_form"):
        if open_players.empty:
            st.warning("Não há jogadores abertos para lance.")
        else:
            player_id = st.selectbox(
                "Jogador",
                open_players["player_id"].tolist(),
                format_func=lambda pid: open_players.loc[open_players["player_id"] == pid, "player_name"].iloc[0]
            )

            if user["role"] == "admin":
                team_name = st.selectbox("Time", list(team_map.keys()))
                team_id = team_map[team_name]
            else:
                st.text_input("Time", value=user.get("team_name", ""), disabled=True)
                team_id = user["team_id"]

            amount = st.number_input("Valor da proposta", min_value=0.0, step=100000.0, format="%.2f")
            years = st.number_input("Anos", min_value=1, max_value=5, step=1)
            submitted = st.form_submit_button("Enviar proposta")

            if submitted:
                ok, msg = submit_bid(player_id, team_id, amount, years, user["username"], user["user_id"])
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

with cap_tab:
    cap_df = pd.DataFrame(get_team_rows())
    st.dataframe(cap_df[["team_name", "cap_limit", "used_cap", "available_cap"]], use_container_width=True, hide_index=True)

with admin_tab:
    if user["role"] != "admin":
        st.warning("Acesso restrito ao administrador.")
    else:
        admin_sub1, admin_sub2, admin_sub3, admin_sub4 = st.tabs(["Jogadores", "Usuários", "Lances", "Auditoria"])

        with admin_sub1:
            players_df = pd.DataFrame(get_players_with_state("Todas"))
            st.dataframe(players_df, use_container_width=True, hide_index=True)
            st.markdown("### Adicionar jogador")
            with st.form("add_player_form"):
                player_name = st.text_input("Nome do jogador")
                position = st.selectbox("Posição", POSITIONS[1:])
                owner_options = {"Sem dono": None}
                owner_options.update({name: tid for name, tid in team_map.items()})
                owner_name = st.selectbox("Dono (renovação)", list(owner_options.keys()))
                add_submit = st.form_submit_button("Adicionar jogador")
                if add_submit and player_name:
                    admin_add_player(player_name, position, owner_options[owner_name], user["username"])
                    st.success("Jogador adicionado.")
                    st.rerun()

            st.markdown("### Ações administrativas")
            if not players_df.empty:
                target_player = st.selectbox(
                    "Selecionar jogador",
                    players_df["player_id"].tolist(),
                    format_func=lambda pid: players_df.loc[players_df["player_id"] == pid, "player_name"].iloc[0],
                    key="admin_player_select"
                )
                col1, col2, col3 = st.columns(3)
                if col1.button("Fechar jogador"):
                    admin_close_player(target_player, user["username"])
                    st.rerun()
                if col2.button("Reabrir jogador"):
                    admin_reopen_player(target_player, user["username"])
                    st.rerun()
                if col3.button("Excluir jogador"):
                    admin_delete_player(target_player, user["username"])
                    st.rerun()

        with admin_sub2:
            users_df = pd.DataFrame(get_all_users())
            st.dataframe(users_df, use_container_width=True, hide_index=True)
            st.markdown("### Criar usuário")
            with st.form("create_user_form"):
                new_username = st.text_input("Usuário novo")
                new_password = st.text_input("Senha nova", type="password")
                new_role = st.selectbox("Perfil", ["admin", "team"])
                team_name_new = st.selectbox("Time do usuário", [""] + list(team_map.keys()))
                create_submit = st.form_submit_button("Criar usuário")
                if create_submit and new_username and new_password:
                    team_id_new = team_map.get(team_name_new) if team_name_new else None
                    create_user(new_username, new_password, new_role, team_id_new)
                    st.success("Usuário criado.")
                    st.rerun()

        with admin_sub3:
            st.markdown("### Remover lance")
            if not players_df.empty:
                target_player_bids = st.selectbox(
                    "Jogador para gerenciar lances",
                    players_df["player_id"].tolist(),
                    format_func=lambda pid: players_df.loc[players_df["player_id"] == pid, "player_name"].iloc[0],
                    key="bid_player_select"
                )
                bids_df = pd.DataFrame(get_bid_history(target_player_bids))
                st.dataframe(bids_df, use_container_width=True, hide_index=True)
                if not bids_df.empty:
                    bid_id = st.selectbox("Bid para excluir", bids_df["bid_id"].tolist())
                    if st.button("Excluir lance selecionado"):
                        admin_delete_bid(bid_id, user["username"])
                        st.success("Lance excluído.")
                        st.rerun()

        with admin_sub4:
            audit_df = pd.DataFrame(get_audit_rows())
            st.dataframe(audit_df, use_container_width=True, hide_index=True)
