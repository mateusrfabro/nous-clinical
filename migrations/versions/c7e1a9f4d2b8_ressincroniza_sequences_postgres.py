"""fix: ressincroniza as sequences do Postgres (bulk_insert com id explicito)

A migration 812bc4e0a35a (multi-tenant fase 0) insere a clinica padrao com
`{"id": 1}` EXPLICITO via op.bulk_insert. No Postgres, informar o id na mao
NAO avanca a sequence da coluna serial -> a sequence continua apontando pro 1
enquanto a linha id=1 ja existe. Resultado: a PRIMEIRA tentativa de criar uma
clinica nova (tela do superadmin) estoura
`UniqueViolation: duplicate key value violates unique constraint "clinicas_pkey"`.

Bug invisivel em dev: o SQLite nao tem sequences, entao so aparece em producao
(Postgres) — classico furo de paridade dev/prod.

Esta migration ressincroniza TODAS as sequences de `id` do schema public
(defensivo: qualquer bulk_insert futuro com id explicito fica coberto).
E idempotente — rodar de novo num banco ja correto nao muda nada.

Revision ID: c7e1a9f4d2b8
Revises: b3f2a1c4d5e6
Create Date: 2026-07-23 17:20:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'c7e1a9f4d2b8'
down_revision = 'b3f2a1c4d5e6'
branch_labels = None
depends_on = None


# setval(seq, GREATEST(max_id, 1), max_id > 0):
#   tabela com linhas  -> proximo id = max(id) + 1
#   tabela vazia       -> proximo id = 1
_RESSINCRONIZA = """
DO $$
DECLARE
    r RECORD;
    seq TEXT;
    mx BIGINT;
BEGIN
    -- Só tabelas que TÊM coluna `id`: pg_get_serial_sequence levanta erro
    -- (não retorna NULL) se a coluna não existir — ex.: alembic_version.
    FOR r IN
        SELECT c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema = 'public'
          AND c.column_name = 'id'
          AND t.table_type = 'BASE TABLE'
    LOOP
        seq := pg_get_serial_sequence(quote_ident(r.table_name), 'id');
        IF seq IS NOT NULL THEN
            EXECUTE format('SELECT COALESCE(MAX(id), 0) FROM %I', r.table_name)
                INTO mx;
            PERFORM setval(seq, GREATEST(mx, 1), mx > 0);
        END IF;
    END LOOP;
END $$;
"""


def upgrade():
    # Só Postgres: SQLite (dev/testes) não tem sequences — vira no-op.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(_RESSINCRONIZA)


def downgrade():
    # Não há o que reverter: a sequence passa a refletir os dados reais.
    # Voltar a dessincronizar de proposito seria recriar o bug.
    pass
