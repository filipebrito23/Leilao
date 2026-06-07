# NBA Auction v3

Versão v3 com arquivos sufixados em `_v3` e nova validação de proposta.

## Arquivos principais

- `app_v3.py`
- `auction_v3.py`
- `auth_v3.py`
- `db_v3.py`
- `import_xlsx_v3.py`
- `test_scenarios_v3.py`
- `requirements_v3.txt`

## Fluxo de uso

1. Coloque `Lista.xlsx` na raiz do projeto.
2. Instale dependências:

```bash
pip install -r requirements_v3.txt
```

3. Rode a importação inicial:

```bash
python import_xlsx_v3.py
```

4. Rode os cenários de teste automatizados:

```bash
python test_scenarios_v3.py
```

5. Suba o app:

```bash
streamlit run app_v3.py
```

## Logins

- Admin padrão: `admin / admin123`
- Usuários de time: nome do time em minúsculas com espaços virando `_`, senha `123456`

## Regra adicional de propostas

- Proposta comum precisa ser maior que a proposta ativa atual.
- Proposta de renovação pode ser igual à proposta ativa, mas não pode ser menor.

## Observação

O banco desta versão é `data/auction_v3.db`, separado das versões anteriores.
