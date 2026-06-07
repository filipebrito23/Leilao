from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from sqlalchemy import text
from streamlit_autorefresh import st_autorefresh
from db_v4 import engine, init_db_v4
from auth_v4 import authenticate_user_v4, get_all_users_v4, create_user_v4, change_password_v4
from auction_v4 import close_expired_bids_v4, submit_bid_v4, get_players_with_state_v4, get_bid_history_v4, get_team_rows_v4, get_audit_rows_v4, admin_add_player_v4, admin_delete_player_v4, admin_reopen_player_v4, admin_close_player_v4, admin_delete_bid_v4

POSITIONS = ["Todas", "PG", "PG_SG", "SG", "SG_SF", "SF", "SF_PF", "PF", "PF_C", "C"]

st.set_page_config(page_title="Leilão NBA Fantasy v4", layout="wide")
init_db_v4()
close_expired_bids_v4()

if "user_v4" not in st.session_state:
    st.session_state.user_v4 = None


def logout_v4():
    st.session_state.user_v4 = None
    st.rerun()


def format_remaining_v4(expires_at):
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


if not st.session_state.user_v4:
    st.title("Leilão NBA Fantasy v4")
    st.subheader("Login por e-mail")
    with st.form("login_form_v4"):
        email = st.text_input("E-mail")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
        if submitted:
            user = authenticate_user_v4(email, password)
            if user:
                st.session_state.user_v4 = user
                st.rerun()
            else:
                st.error("E-mail ou senha inválidos.")
    #st.info("Admin padrão: admin@auction.local / admin123")
    st.stop()

user = st.session_state.user_v4
st.sidebar.success(f"Logado como: {user['email']} ({user['role']})")
if user.get("team_name"):
    st.sidebar.write(f"Time vinculado: {user['team_name']}")
st.sidebar.button("Sair", on_click=logout_v4)

if user.get("must_change_password") == 1:
    st.warning("Você precisa trocar sua senha antes de continuar.")
    with st.form("change_password_first_login_v4"):
        new_password = st.text_input("Nova senha", type="password")
        confirm_password = st.text_input("Confirmar nova senha", type="password")
        submit_change = st.form_submit_button("Salvar nova senha")
        if submit_change:
            if not new_password or len(new_password) < 6:
                st.error("A senha deve ter pelo menos 6 caracteres.")
            elif new_password != confirm_password:
                st.error("As senhas não coincidem.")
            else:
                change_password_v4(user["user_id"], new_password)
                st.session_state.user_v4["must_change_password"] = 0
                st.success("Senha alterada com sucesso.")
                st.rerun()
    st.stop()

st_autorefresh(interval=20000, key="auction_refresh_v4")

st.title("Leilão NBA Fantasy v4")
main_tab, bid_tab, cap_tab, admin_tab, profile_tab = st.tabs(["Propostas", "Nova proposta", "Cap", "Admin", "Perfil"])

with main_tab:
    position = st.selectbox("Posição", POSITIONS)
    players = pd.DataFrame(get_players_with_state_v4(position))
    if not players.empty:
        players["tempo_restante"] = players["expires_at"].apply(format_remaining_v4)
        players["tipo"] = players["is_renewal"].apply(lambda x: "Renovação" if x == 1 else "Oferta")
        st.dataframe(players[["player_id", "player_name", "position", "dono", "time_ativo", "proposta_ativa", "anos", "active_at", "expires_at", "tempo_restante", "tipo", "status"]], use_container_width=True, hide_index=True)
        selected_player = st.selectbox("Ver histórico do jogador", players["player_id"].tolist(), format_func=lambda pid: players.loc[players["player_id"] == pid, "player_name"].iloc[0])
        history = pd.DataFrame(get_bid_history_v4(selected_player))
        st.markdown("### Histórico do jogador")
        if not history.empty:
            history["tipo"] = history["is_renewal"].apply(lambda x: "Renovação" if x == 1 else "Oferta")
            history["ativa"] = history["is_active"].apply(lambda x: "Sim" if x == 1 else "Não")
            st.dataframe(history[["bid_id", "team_name", "amount", "years", "created_at", "tipo", "ativa", "created_by"]], use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma proposta para este jogador ainda.")

with bid_tab:
    players = pd.DataFrame(get_players_with_state_v4("Todas"))
    open_players = players[players["status"] == "OPEN"] if not players.empty else pd.DataFrame()
    with engine.begin() as conn:
        teams = conn.execute(text("SELECT team_id, team_name FROM teams ORDER BY team_name")).fetchall()
    team_map = {name: tid for tid, name in teams}
    with st.form("bid_form_v4"):
        if open_players.empty:
            st.warning("Não há jogadores abertos para lance.")
        else:
            player_id = st.selectbox("Jogador", open_players["player_id"].tolist(), format_func=lambda pid: open_players.loc[open_players["player_id"] == pid, "player_name"].iloc[0])
            selected_row = open_players.loc[open_players["player_id"] == player_id].iloc[0]
            st.write(f"Proposta ativa atual: {selected_row['proposta_ativa'] if pd.notna(selected_row['proposta_ativa']) else '-'}")
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
                ok, msg = submit_bid_v4(player_id, team_id, amount, years, user["email"], user["user_id"], user["role"], user.get("team_id"))
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

with cap_tab:
    cap_df = pd.DataFrame(get_team_rows_v4())
    st.dataframe(cap_df[["team_name", "cap_limit", "used_cap", "available_cap"]], use_container_width=True, hide_index=True)

with admin_tab:
    if user["role"] != "admin":
        st.warning("Acesso restrito ao administrador.")
    else:
        with engine.begin() as conn:
            teams = conn.execute(text("SELECT team_id, team_name FROM teams ORDER BY team_name")).fetchall()
        team_map = {name: tid for tid, name in teams}
        admin_sub1, admin_sub2, admin_sub3, admin_sub4 = st.tabs(["Jogadores", "Usuários", "Lances", "Auditoria"])
        with admin_sub1:
            players_df = pd.DataFrame(get_players_with_state_v4("Todas"))
            st.dataframe(players_df, use_container_width=True, hide_index=True)
            with st.form("add_player_form_v4"):
                player_name = st.text_input("Nome do jogador")
                position = st.selectbox("Posição", POSITIONS[1:])
                owner_options = {"Sem dono": None}
                owner_options.update({name: tid for name, tid in team_map.items()})
                owner_name = st.selectbox("Dono (renovação)", list(owner_options.keys()))
                add_submit = st.form_submit_button("Adicionar jogador")
                if add_submit and player_name:
                    admin_add_player_v4(player_name, position, owner_options[owner_name], user["email"])
                    st.success("Jogador adicionado.")
                    st.rerun()
            if not players_df.empty:
                target_player = st.selectbox("Selecionar jogador", players_df["player_id"].tolist(), format_func=lambda pid: players_df.loc[players_df["player_id"] == pid, "player_name"].iloc[0], key="admin_player_select_v4")
                c1, c2, c3 = st.columns(3)
                if c1.button("Fechar jogador"):
                    admin_close_player_v4(target_player, user["email"])
                    st.rerun()
                if c2.button("Reabrir jogador"):
                    admin_reopen_player_v4(target_player, user["email"])
                    st.rerun()
                if c3.button("Excluir jogador"):
                    admin_delete_player_v4(target_player, user["email"])
                    st.rerun()
        with admin_sub2:
            users_df = pd.DataFrame(get_all_users_v4())
            st.dataframe(users_df, use_container_width=True, hide_index=True)
            with st.form("create_user_form_v4"):
                new_email = st.text_input("E-mail do usuário")
                new_password = st.text_input("Senha inicial", type="password")
                new_role = st.selectbox("Perfil", ["admin", "team"])
                team_name_new = st.selectbox("Time do usuário", [""] + list(team_map.keys()))
                create_submit = st.form_submit_button("Criar usuário")
                if create_submit and new_email and new_password:
                    team_id_new = team_map.get(team_name_new) if team_name_new else None
                    create_user_v4(new_email, new_password, new_role, team_id_new, must_change_password=1)
                    st.success("Usuário criado.")
                    st.rerun()
        with admin_sub3:
            players_df = pd.DataFrame(get_players_with_state_v4("Todas"))
            if not players_df.empty:
                target_player_bids = st.selectbox("Jogador para gerenciar lances", players_df["player_id"].tolist(), format_func=lambda pid: players_df.loc[players_df["player_id"] == pid, "player_name"].iloc[0], key="bid_player_select_v4")
                bids_df = pd.DataFrame(get_bid_history_v4(target_player_bids))
                st.dataframe(bids_df, use_container_width=True, hide_index=True)
                if not bids_df.empty:
                    bid_id = st.selectbox("Bid para excluir", bids_df["bid_id"].tolist())
                    if st.button("Excluir lance selecionado"):
                        admin_delete_bid_v4(bid_id, user["email"])
                        st.success("Lance excluído.")
                        st.rerun()
        with admin_sub4:
            audit_df = pd.DataFrame(get_audit_rows_v4())
            st.dataframe(audit_df, use_container_width=True, hide_index=True)

with profile_tab:
    st.subheader("Alterar senha")
    with st.form("change_password_profile_v4"):
        new_password = st.text_input("Nova senha", type="password", key="profile_new_password_v4")
        confirm_password = st.text_input("Confirmar nova senha", type="password", key="profile_confirm_password_v4")
        submit_password = st.form_submit_button("Atualizar senha")
        if submit_password:
            if not new_password or len(new_password) < 6:
                st.error("A senha deve ter pelo menos 6 caracteres.")
            elif new_password != confirm_password:
                st.error("As senhas não coincidem.")
            else:
                change_password_v4(user["user_id"], new_password)
                st.success("Senha atualizada com sucesso.")
