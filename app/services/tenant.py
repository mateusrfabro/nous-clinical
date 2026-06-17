"""Multi-tenant Fase 1 — escopo automático por clínica (defesa em profundidade).

Em vez de confiar que toda query lembre de filtrar por clinica_id (fácil
esquecer = vazamento entre clínicas), aplicamos o filtro AUTOMATICAMENTE via
event `do_orm_execute` (with_loader_criteria). E setamos clinica_id nas linhas
novas via `before_flush`. Assim:

- READ: toda SELECT das entidades do tenant ganha `clinica_id == <atual>` sem
  o caller fazer nada. Esquecer um filtro não vaza.
- WRITE: linha nova sem clinica_id recebe a clínica atual (ou, em contexto sem
  request — seed/job/teste single-tenant — a única clínica existente).

A clínica atual vem de `g.clinica_id`, populado no before_request a partir do
current_user. Usuario NÃO é escopado na leitura (o login precisa achar o user
antes de saber a clínica). clinica_id segue NULLABLE nesta fase (NOT NULL é
hardening posterior). Ver docs/arquitetura/0001-multi-tenant-rbac.md.
"""
from flask import g, has_request_context
from sqlalchemy import event, select
from sqlalchemy.orm import Session, with_loader_criteria


def clinica_atual():
    if has_request_context():
        return getattr(g, "clinica_id", None)
    return None


def _clinica_unica(session):
    """Fallback single-tenant: se existe exatamente 1 clínica, é ela."""
    from app.models import Clinica
    ids = session.execute(select(Clinica.id).limit(2)).scalars().all()
    return ids[0] if len(ids) == 1 else None


def init_tenant(db):
    """Registra os listeners de escopo. Chamado uma vez no app factory."""
    from app.models import (
        Paciente, Profissional, Agendamento, Atendimento,
        LancamentoFinanceiro, Procedimento, Exame, Convenio, Usuario, Bloqueio,
    )
    # Escopo de LEITURA (sem Usuario — auth precisa de lookup global).
    escopados = [Paciente, Profissional, Agendamento, Atendimento,
                 LancamentoFinanceiro, Procedimento, Exame, Convenio, Bloqueio]
    # Recebem clinica_id na CRIAÇÃO (inclui Usuario).
    donos = tuple(escopados + [Usuario])

    @event.listens_for(Session, "do_orm_execute")
    def _aplica_escopo(state):
        if (not state.is_select or state.is_column_load
                or state.is_relationship_load):
            return
        if state.execution_options.get("ignore_tenant"):
            return
        cid = clinica_atual()
        if cid is None:
            return
        for modelo in escopados:
            state.statement = state.statement.options(
                with_loader_criteria(
                    modelo, modelo.clinica_id == cid, include_aliases=True)
            )

    @event.listens_for(Session, "before_flush")
    def _seta_clinica(session, flush_ctx, instances):
        cid = clinica_atual() or _clinica_unica(session)
        if cid is None:
            return
        for obj in session.new:
            if isinstance(obj, donos) and getattr(obj, "clinica_id", None) is None:
                obj.clinica_id = cid
