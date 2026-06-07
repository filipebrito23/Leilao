# NBA Auction v2 nomeada

Versão v2 com arquivos sufixados em `_v2` para manter histórico de versões.

## Arquivos principais

- `app_v2.py`
- `auction_v2.py`
- `auth_v2.py`
- `db_v2.py`
- `import_xlsx_v2.py`
- `test_scenarios_v2.py`
- `requirements_v2.txt`

## Fluxo de uso

1. Coloque `Lista.xlsx` na raiz do projeto.
2. Instale dependências:

```bash
pip install -r requirements_v2.txt
```

3. Rode a importação inicial:

```bash
python import_xlsx_v2.py
```

4. Rode os cenários de teste automatizados:

```bash
python test_scenarios_v2.py
```

5. Suba o app:

```bash
streamlit run app_v2.py
```

## Logins

- Admin padrão: `admin / admin123`
- Usuários de time: nome do time em minúsculas com espaços virando `_`, senha `123456`

## Cenários automatizados incluídos

- lance normal
- renovação ativa
- troca de liderança no mesmo jogador
- exclusão de lance pelo admin
- fechamento após 24h
- bloqueio de usuário comum tentando lançar por outro time

## Observação

O banco desta versão é `data/auction_v2.db`, separado das versões anteriores.
