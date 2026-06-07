# NBA Auction v4

Versão v4 com login por e-mail e senha, múltiplos usuários por time e hash de senha com bcrypt.

## Arquivos principais

- `app_v4.py`
- `auction_v4.py`
- `auth_v4.py`
- `db_v4.py`
- `import_xlsx_v4.py`
- `test_scenarios_v4.py`
- `requirements_v4.txt`

## Fluxo de uso

1. Coloque `Lista.xlsx` na raiz do projeto.
2. Instale dependências:

```bash
pip install -r requirements_v4.txt
```

3. Rode a importação inicial:

```bash
python import_xlsx_v4.py
```

4. Rode os cenários de teste:

```bash
python test_scenarios_v4.py
```

5. Suba o app:

```bash
streamlit run app_v4.py
```

## Login

- Admin padrão: `admin@auction.local / admin123`
- Usuários de exemplo por time: `<nome_do_time>@auction.local` com senha inicial `123456`
- Usuários de time precisam trocar a senha no primeiro acesso

## Mudanças da v4

- Login passa a ser por e-mail e senha
- Múltiplos usuários podem ser cadastrados para o mesmo time
- Senhas usam hash com `bcrypt`
- Tela de troca de senha incluída
