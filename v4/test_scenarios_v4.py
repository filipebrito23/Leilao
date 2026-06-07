from sqlalchemy import text
from db_v4 import engine, init_db_v4
from auth_v4 import create_user_v4, authenticate_user_v4, change_password_v4


def main():
    init_db_v4()
    results = []
    with engine.begin() as conn:
        team = conn.execute(text("SELECT team_id, team_name FROM teams LIMIT 1")).fetchone()
    if team:
        try:
            create_user_v4("tester1@auction.local", "abc123", "team", team[0], must_change_password=1)
            results.append(("criação de usuário por email", True, "usuário criado"))
        except Exception as e:
            results.append(("criação de usuário por email", False, str(e)))
        user = authenticate_user_v4("tester1@auction.local", "abc123")
        results.append(("login por email e senha", user is not None, "login ok" if user else "login falhou"))
        if user:
            change_password_v4(user["user_id"], "nova123")
            user2 = authenticate_user_v4("tester1@auction.local", "nova123")
            results.append(("troca de senha", user2 is not None, "senha alterada" if user2 else "troca falhou"))
    print("CENÁRIOS DE TESTE V4")
    for name, ok, msg in results:
        print(f"- {name}: {'OK' if ok else 'FALHOU'} | {msg}")


if __name__ == '__main__':
    main()
