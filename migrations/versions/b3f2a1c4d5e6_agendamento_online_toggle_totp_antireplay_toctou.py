"""agendamento online toggle + anti-replay TOTP + trava TOCTOU de horario

Revision ID: b3f2a1c4d5e6
Revises: 0a6769eb496e
Create Date: 2026-07-02 15:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f2a1c4d5e6'
down_revision = '0a6769eb496e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('clinicas', schema=None) as batch_op:
        # server_default false: sem ele o ADD COLUMN NOT NULL falha em tabela com
        # linhas no Postgres. Default do produto = agendamento online DESLIGADO.
        batch_op.add_column(sa.Column('agendamento_online_ativo', sa.Boolean(),
                                      nullable=False, server_default=sa.false()))

    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('totp_ultimo_contador', sa.BigInteger(),
                                      nullable=True))

    # Índice único PARCIAL (fora do batch: SQLite adiciona índice sem recriar a
    # tabela, e a cláusula WHERE precisa do kwarg de dialeto). Trava a colisão de
    # (profissional, início exato) entre agendamentos não-cancelados.
    op.create_index('uq_ag_prof_inicio_ativo', 'agendamentos',
                    ['profissional_id', 'inicio'], unique=True,
                    sqlite_where=sa.text("status != 'cancelado'"),
                    postgresql_where=sa.text("status != 'cancelado'"))


def downgrade():
    op.drop_index('uq_ag_prof_inicio_ativo', table_name='agendamentos')

    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_column('totp_ultimo_contador')

    with op.batch_alter_table('clinicas', schema=None) as batch_op:
        batch_op.drop_column('agendamento_online_ativo')
