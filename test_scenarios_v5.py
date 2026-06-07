from sqlalchemy import text
from db_v5 import engine, init_db_v5
from auth_v5 import create_user_v5, authenticate_user_v5, change_password_v5


def main():
    init_db_v5()
    results = []

    with engine.begin() as conn:
        team = conn.execute(text("""
            SELECT team_id, team_name
            FROM teams
            LIMIT 1
        """)).fetchone()

    if not team:
        print("Nenhum time cadastrado. Rode antes o import_xlsx_v5.py.")
        return

    team_id = team[0]

    try:
        create_user_v5(
            "tester1@auction.local",
            "abc123",
            "team",
            team_id,
            must_change_password=1
        )
        results.append(("criação de usuário por email", True, "usuário criado"))
    except Exception as e:
        results.append(("criação de usuário por email", False, str(e)))

    user = authenticate_user_v5("tester1@auction.local", "abc123")
    results.append((
        "login por email e senha",
        user is not None,
        "login ok" if user else "login falhou"
    ))

    if user:
        try:
            change_password_v5(user["user_id"], "nova123")
            user2 = authenticate_user_v5("tester1@auction.local", "nova123")
            results.append((
                "troca de senha",
                user2 is not None,
                "senha alterada" if user2 else "troca falhou"
            ))
        except Exception as e:
            results.append(("troca de senha", False, str(e)))

    print("CENÁRIOS DE TESTE V5")
    for name, ok, msg in results:
        print(f"- {name}: {'OK' if ok else 'FALHOU'} | {msg}")


if __name__ == "__main__":
    main()