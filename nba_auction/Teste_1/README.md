# NBA Auction v2

Versão evoluída do MVP com autenticação, perfil admin, histórico do jogador, contador regressivo, autorefresh e estrutura pronta para futura migração para Postgres.

## Recursos

- Login local com usuários no banco
- Usuário admin padrão: `admin` / `admin123`
- Usuários de time gerados automaticamente com senha padrão `123456`
- Trava por time: usuário comum só lança pelo próprio time
- Perfil admin com ações de gerenciamento
- Histórico de propostas por jogador
- Contador de tempo restante até encerrar em 24h
- Renovação aparece como proposta ativa, mas não consome cap
- Refresh automático leve na tela
- Estrutura preparada para usar `DATABASE_URL` no futuro com Postgres

## Arquivos

- `app.py`: interface Streamlit
- `db.py`: conexão e criação do banco
- `auth.py`: autenticação local
- `auction.py`: regras de negócio e administração
- `import_xlsx.py`: carga inicial da planilha
- `requirements.txt`: dependências

## Como usar

1. Coloque `Lista.xlsx` na raiz do projeto.
2. Instale as dependências:

```bash
pip install -r requirements.txt
```

3. Importe a base inicial:

```bash
python import_xlsx.py
```

4. Rode o app:

```bash
streamlit run app.py
```

## Observações

- A senha padrão dos usuários de time é `123456`.
- Para produção, troque o hash simples por `bcrypt` e mova para Postgres.
- O `DATABASE_URL` pode ser definido como variável de ambiente para futura migração.
