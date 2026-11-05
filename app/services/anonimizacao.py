"""Anonimização de paciente — LGPD art. 18 (direito ao esquecimento).

Anonimiza em vez de deletar: zera os dados PESSOAIS (PII) do cadastro e apaga o
conteúdo CLÍNICO (prontuário + arquivos de exame), mas PRESERVA os lançamentos
financeiros (valor/data/forma de pagamento) sem o nome — a legislação fiscal
exige a guarda desses registros. Operação IRREVERSÍVEL.

A trilha de auditoria (AuditLog) não guarda PII, então permanece intacta.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app import db
from app.models import Exame, LancamentoFinanceiro
from app.services.storage import get_storage

logger = logging.getLogger(__name__)


def anonimizar_paciente(paciente):
    """Anonimiza o paciente in-place (o caller faz commit + audit).

    Retorna a contagem do que foi tocado (pra registrar no audit sem PII).
    """
    pid = paciente.id

    # 1) Zera a PII do cadastro.
    paciente.nome_completo = f"Paciente removido #{pid}"
    paciente.cpf = None
    paciente.data_nascimento = None
    paciente.sexo = None
    paciente.telefone = None
    paciente.email = None
    paciente.cep = None
    paciente.endereco = None
    paciente.bairro = None
    paciente.cidade = None
    paciente.observacoes = None
    paciente.ativo = False
    paciente.anonimizado_em = datetime.now(timezone.utc)

    # 2) Apaga o conteúdo CLÍNICO do prontuário (dado sensível), preservando o
    #    registro (rastro de que a consulta existiu, sem o conteúdo).
    n_atend = 0
    for at in paciente.atendimentos:
        at.queixa = None
        at.evolucao = None
        at.prescricao = None
        at.atestado_cid = None
        n_atend += 1

    # 3) Apaga os EXAMES (arquivos sensíveis) do storage + os registros.
    storage = get_storage()
    exames = db.session.execute(
        select(Exame).where(Exame.paciente_id == pid)
    ).scalars().all()
    n_exames = 0
    for ex in exames:
        try:
            storage.delete(ex.arquivo_key)
        except FileNotFoundError:
            pass
        except Exception:   # noqa: BLE001
            logger.warning("ANON_EXAME_STORAGE_FALHA exame=%s", ex.id, exc_info=True)
        db.session.delete(ex)
        n_exames += 1

    # 4) Remove PII de textos livres nos agendamentos.
    for ag in paciente.agendamentos:
        ag.observacoes = None

    # 5) Financeiro: PRESERVA valor/data/forma (obrigação fiscal); só tira o nome
    #    da descrição, que pode conter PII. Mantém o vínculo paciente_id.
    lancs = db.session.execute(
        select(LancamentoFinanceiro).where(LancamentoFinanceiro.paciente_id == pid)
    ).scalars().all()
    for lanc in lancs:
        lanc.descricao = f"Lançamento (paciente anonimizado #{pid})"

    logger.info("PACIENTE_ANONIMIZADO id=%s atend=%s exames=%s lanc=%s",
                pid, n_atend, n_exames, len(lancs))
    return {"atendimentos": n_atend, "exames": n_exames, "lancamentos": len(lancs)}
