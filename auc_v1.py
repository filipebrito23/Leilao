from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from sqlalchemy import text
from streamlit_autorefresh import st_autorefresh

from db_v5 import engine, init_db_v5, healthcheck_db_v5, is_postgres_v5
from auth_v5 import (
    authenticate_user_v5,
    get_all_users_v5,
    create_user_v5,
    change_password_v5
)
from auction_v5 import (
    close_expired_bids_v5,
    submit_bid_v5,
    get_players_with_state_v5,
    get_bid_history_v5,
    get_team_rows_v5,
    get_audit_rows_v5
)

POSITIONS = ["Todas", "PG", "PG_SG", "SG", "SG_SF", "SF", "SF_PF", "PF", "PF_C", "C"]

st.set_page_config(page_title="Leilão NBA Fantasy v5", layout="wide")


def get_environment_label_v5():
    app_cfg = st.secrets.get("app", {})
    return str(app_cfg.get("environment", "development")).lower()


def startup_v5():
    try:
        healthcheck_db_v5()
        init_db_v5()
        close_expired_bids_v5()
        return True, None
    except Exception as e:
        return False, str(e)


ok_startup, startup_error = startup_v5()

if not ok_startup:
    st.error(f"Erro ao inicializar aplicação: {startup_error}")
    st.stop()

if "user_v5" not in st.session_state:
    st.session_state.user_v5 = None


def logout_v5():
    st.session_state.user_v5 = None
    st.rerun()

def formatar_br(valor):
         """Formatar 1000000.0 -> 1.000.000,00"""
         return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def format_remaining_v5(expires_at):
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


st.sidebar.caption(f"Ambiente: {get_environment_label_v5()}")
st.sidebar.caption(f"Banco: {'PostgreSQL' if is_postgres_v5() else 'SQLite'}")

if not st.session_state.user_v5:
    st.title("Leilão NBA Fantasy v5")
    st.subheader("Login por e-mail")

    with st.form("login_form_v5"):
        email = st.text_input("E-mail")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")

        if submitted:
            user = authenticate_user_v5(email, password)
            if user:
                st.session_state.user_v5 = user
                st.rerun()
            else:
                st.error("E-mail ou senha inválidos.")

    st.stop()

user = st.session_state.user_v5

st.sidebar.success(f"Logado como: {user['email']} ({user['role']})")
if user.get("team_name"):
    st.sidebar.write(f"Time vinculado: {user['team_name']}")
st.sidebar.button("Sair", on_click=logout_v5)

if user.get("must_change_password") == 1:
    st.warning("Você precisa trocar sua senha antes de continuar.")

    with st.form("change_password_first_login_v5"):
        new_password = st.text_input("Nova senha", type="password")
        confirm_password = st.text_input("Confirmar nova senha", type="password")
        submit_change = st.form_submit_button("Salvar nova senha")

        if submit_change:
            if not new_password or len(new_password) < 6:
                st.error("A senha deve ter pelo menos 6 caracteres.")
            elif new_password != confirm_password:
                st.error("As senhas não coincidem.")
            else:
                change_password_v5(user["user_id"], new_password)
                st.session_state.user_v5["must_change_password"] = 0
                st.success("Senha alterada com sucesso.")
                st.rerun()

    st.stop()

#st_autorefresh(interval=20000, key="auction_refresh_v5")

st.title("Leilão NBA Fantasy v5")

main_tab, bid_tab, cap_tab, admin_tab, profile_tab = st.tabs(
    ["Propostas", "Nova proposta", "Cap", "Admin", "Perfil"]
)

with main_tab:
    position = st.selectbox("Posição", POSITIONS)
    players = pd.DataFrame(get_players_with_state_v5(position))

    if not players.empty:
        players["tempo_restante"] = players["expires_at"].apply(format_remaining_v5)
        players["tipo"] = players["is_renewal"].apply(
            lambda x: "Renovação" if x == 1 else "Oferta"
        )

        st.dataframe(
            players[
                [
                    "player_name",
                    "position",
                    "dono",
                    "time_ativo",
                    "proposta_ativa",
                    "anos",
                    "tempo_restante",
                    "tipo",
                    "status",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        selected_player = st.selectbox(
            "Ver histórico do jogador",
            players["player_id"].tolist(),
            format_func=lambda pid: players.loc[
                players["player_id"] == pid, "player_name"
            ].iloc[0],
        )

        history = pd.DataFrame(get_bid_history_v5(selected_player))
        st.markdown("### Histórico do jogador")

        if not history.empty:
            history["tipo"] = history["is_renewal"].apply(
                lambda x: "Renovação" if x == 1 else "Oferta"
            )
            history["ativa"] = history["is_active"].apply(
                lambda x: "Sim" if x == 1 else "Não"
            )

            st.dataframe(
                history[
                    [
                        "bid_id",
                        "team_name",
                        "amount",
                        "years",
                        "created_at",
                        "tipo",
                        "ativa",
                        "created_by",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Nenhuma proposta para este jogador ainda.")
    else:
        st.info("Nenhum jogador encontrado para o filtro atual.")

with bid_tab:
    players = pd.DataFrame(get_players_with_state_v5("Todas"))
    open_players = players[players["status"] == "OPEN"] if not players.empty else pd.DataFrame()

    with engine.begin() as conn:
        teams = conn.execute(text("""
            SELECT team_id, team_name
            FROM teams
            ORDER BY team_name
        """)).fetchall()

    team_map = {name: tid for tid, name in teams}

    with st.form("bid_form_v5"):
        if open_players.empty:
            st.warning("Não há jogadores abertos para lance.")
        else:
            player_id = st.selectbox(
                "Jogador",
                open_players["player_id"].tolist(),
                format_func=lambda pid: open_players.loc[
                    open_players["player_id"] == pid, "player_name"
                ].iloc[0],
            )

            selected_row = open_players.loc[open_players["player_id"] == player_id].iloc[0]

            st.write(
                f"Proposta ativa atual: "
                f"{selected_row['proposta_ativa'] if pd.notna(selected_row['proposta_ativa']) else '-'}"
            )

            if user["role"] == "admin":
                team_name = st.selectbox("Time", list(team_map.keys()))
                team_id = team_map[team_name]
            else:
                st.text_input("Time", value=user.get("team_name", ""), disabled=True)
                team_id = user["team_id"]

            amount = st.number_input(
                "Valor da proposta",
                min_value=1000000.0,
                step=100000.0,
                format="%.2f"
            )
            years = st.number_input("Anos", min_value=1, max_value=4, step=1)

            submitted = st.form_submit_button("Enviar proposta")

            if submitted:
                ok, msg = submit_bid_v5(
                    player_id,
                    team_id,
                    amount,
                    years,
                    user["email"],
                    user["user_id"],
                    user["role"],
                    user.get("team_id")
                )

                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

with cap_tab:
    cap_df = pd.DataFrame(get_team_rows_v5())

    if not cap_df.empty:
        st.dataframe(
            cap_df[["team_name", "cap_limit", "used_cap", "available_cap"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Nenhum time carregado.")

with admin_tab:
    if user["role"] != "admin":
        st.warning("Acesso restrito ao administrador.")
    else:
        st.subheader("Usuários")

        users_df = pd.DataFrame(get_all_users_v5())
        if not users_df.empty:
            st.dataframe(users_df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum usuário cadastrado.")

        with engine.begin() as conn:
            teams = conn.execute(text("""
                SELECT team_id, team_name
                FROM teams
                ORDER BY team_name
            """)).fetchall()

        team_map = {name: tid for tid, name in teams}

        with st.form("create_user_form_v5"):
            new_email = st.text_input("E-mail do usuário")
            new_password = st.text_input("Senha inicial", type="password")
            new_role = st.selectbox("Perfil", ["admin", "team"])
            team_name_new = st.selectbox("Time do usuário", [""] + list(team_map.keys()))
            create_submit = st.form_submit_button("Criar usuário")

            if create_submit:
                if not new_email or not new_password:
                    st.error("Preencha e-mail e senha.")
                else:
                    try:
                        team_id_new = team_map.get(team_name_new) if team_name_new else None
                        create_user_v5(
                            new_email,
                            new_password,
                            new_role,
                            team_id_new,
                            must_change_password=1
                        )
                        st.success("Usuário criado.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao criar usuário: {e}")

        st.subheader("Auditoria")
        audit_df = pd.DataFrame(get_audit_rows_v5())

        if not audit_df.empty:
            st.dataframe(audit_df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum evento de auditoria.")

with profile_tab:
    st.subheader("Alterar senha")

    with st.form("change_password_profile_v5"):
        new_password = st.text_input("Nova senha", type="password", key="profile_new_password_v5")
        confirm_password = st.text_input("Confirmar nova senha", type="password", key="profile_confirm_password_v5")
        submit_password = st.form_submit_button("Atualizar senha")

        if submit_password:
            if not new_password or len(new_password) < 6:
                st.error("A senha deve ter pelo menos 6 caracteres.")
            elif new_password != confirm_password:
                st.error("As senhas não coincidem.")
            else:
                try:
                    change_password_v5(user["user_id"], new_password)
                    st.success("Senha atualizada com sucesso.")
                except Exception as e:
                    st.error(f"Erro ao atualizar senha: {e}")