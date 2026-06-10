"""Geração de documentos clínicos em PDF (A4): receita/prescrição e atestado.

Server-side (reportlab) — sem dependência de browser. Cabeçalho com a logo da
clínica quando cadastrada (raster no storage); senão, o wordmark padrão
"Nous Clinical". Dados do médico logado preenchidos automaticamente.
"""
import io
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

from app import db
from app.models import Clinica
from app.services.storage import get_storage

_BR = ZoneInfo("America/Sao_Paulo")
_MESES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
          "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
_BRAND = colors.HexColor("#43B8A5")
_INK = colors.HexColor("#1E293B")


def _data_extenso(d):
    return f"{d.day:02d} de {_MESES[d.month]} de {d.year}"


def _estilos():
    base = getSampleStyleSheet()
    return {
        "marca": ParagraphStyle(
            "marca", parent=base["Title"], fontSize=22, leading=26,
            textColor=_BRAND, alignment=TA_CENTER, spaceAfter=2),
        "titulo": ParagraphStyle(
            "titulo", parent=base["Heading1"], fontSize=15, leading=19,
            textColor=_INK, alignment=TA_CENTER, spaceBefore=8, spaceAfter=2),
        "medico": ParagraphStyle(
            "medico", parent=base["Normal"], fontSize=11, leading=15,
            textColor=_INK, alignment=TA_CENTER),
        "muted": ParagraphStyle(
            "muted", parent=base["Normal"], fontSize=10, leading=14,
            textColor=colors.HexColor("#64748B"), alignment=TA_CENTER),
        "campo": ParagraphStyle(
            "campo", parent=base["Normal"], fontSize=11, leading=18,
            textColor=_INK),
        "corpo": ParagraphStyle(
            "corpo", parent=base["Normal"], fontSize=11.5, leading=18,
            textColor=_INK, alignment=TA_JUSTIFY, spaceBefore=6),
        "assin": ParagraphStyle(
            "assin", parent=base["Normal"], fontSize=11, leading=15,
            textColor=_INK, alignment=TA_CENTER),
    }


def _registro_label(prof):
    """Texto do conselho (ex.: 'CRM-PR 12345'). '' se não cadastrado."""
    reg = (prof.registro_conselho or "").strip() if prof else ""
    if not reg:
        return ""
    # Se já vem com letras (CRM/CRO/...), mantém; senão prefixa CRM.
    return reg if any(c.isalpha() for c in reg) else f"CRM {reg}"


def _logo_flowable(clinica):
    """Logo raster da clínica centralizada (ou None se não houver/falhar)."""
    if not (clinica and clinica.logo_key):
        return None
    try:
        dados = get_storage().read(clinica.logo_key)
        ir = ImageReader(io.BytesIO(dados))
        iw, ih = ir.getSize()
        if not iw or not ih:
            return None
        max_w, max_h = 50 * mm, 24 * mm
        escala = min(max_w / iw, max_h / ih)
        img = Image(io.BytesIO(dados), width=iw * escala, height=ih * escala)
        img.hAlign = "CENTER"
        return img
    except Exception:
        return None


def _cabecalho(story, estilos, clinica, prof, titulo):
    logo = _logo_flowable(clinica)
    if logo is not None:
        story.append(logo)
    else:
        nome = (clinica.nome if clinica and clinica.nome else "Nous Clinical")
        story.append(Paragraph(nome, estilos["marca"]))
    story.append(Paragraph(titulo, estilos["titulo"]))
    if prof and prof.nome:
        story.append(Paragraph(prof.nome, estilos["medico"]))
    reg = _registro_label(prof)
    if reg:
        story.append(Paragraph(reg, estilos["muted"]))
    story.append(Spacer(1, 10 * mm))


def _doc(buf):
    return SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title="Documento clínico", author="Nous Clinical")


def _rodape_assinatura(story, estilos, prof, data):
    story.append(Spacer(1, 18 * mm))
    story.append(Paragraph(f"____________________, {_data_extenso(data)}.",
                           estilos["assin"]))
    story.append(Spacer(1, 14 * mm))
    story.append(Paragraph("_________________________________________",
                           estilos["assin"]))
    if prof and prof.nome:
        story.append(Paragraph(prof.nome, estilos["assin"]))
    reg = _registro_label(prof)
    if reg:
        story.append(Paragraph(reg, estilos["muted"]))


def _escape(txt):
    """Escapa para o mini-HTML do Paragraph e preserva quebras de linha."""
    s = (txt or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return s.replace("\r\n", "\n").replace("\n", "<br/>")


def _clinica_e_data(atendimento):
    clinica = db.session.get(Clinica, atendimento.clinica_id) \
        if atendimento.clinica_id else None
    criado = atendimento.criado_em
    if criado is not None and criado.tzinfo is None:
        from datetime import timezone
        criado = criado.replace(tzinfo=timezone.utc)
    data = criado.astimezone(_BR).date() if criado else None
    if data is None:
        from datetime import datetime, timezone
        data = datetime.now(timezone.utc).astimezone(_BR).date()
    return clinica, data


def receita_pdf(atendimento):
    """Bytes do PDF de prescrição/receita médica de um atendimento."""
    estilos = _estilos()
    clinica, data = _clinica_e_data(atendimento)
    prof = atendimento.profissional
    pac = atendimento.paciente

    buf = io.BytesIO()
    doc = _doc(buf)
    story = []
    _cabecalho(story, estilos, clinica, prof, "Prescrição Médica")

    story.append(Paragraph(
        f"<b>Nome do Paciente:</b> {_escape(pac.nome_completo) if pac else ''}",
        estilos["campo"]))
    story.append(Paragraph(
        f"<b>CPF:</b> {_escape(pac.cpf) if pac and pac.cpf else '________________'}",
        estilos["campo"]))
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph(_escape(atendimento.prescricao), estilos["corpo"]))

    _rodape_assinatura(story, estilos, prof, data)
    doc.build(story)
    return buf.getvalue()


def atestado_pdf(atendimento):
    """Bytes do PDF de atestado médico de um atendimento."""
    estilos = _estilos()
    clinica, data = _clinica_e_data(atendimento)
    prof = atendimento.profissional
    pac = atendimento.paciente
    dias = atendimento.atestado_dias or 0
    cid = (atendimento.atestado_cid or "").strip()

    nome = pac.nome_completo if pac else "________________"
    cpf = pac.cpf if (pac and pac.cpf) else "________________"

    buf = io.BytesIO()
    doc = _doc(buf)
    story = []
    _cabecalho(story, estilos, clinica, prof, "Atestado Médico")

    corpo = (
        f"ATESTO, para os devidos fins, que o(a) paciente <b>{_escape(nome)}</b>, "
        f"portador(a) do CPF nº {_escape(cpf)}, esteve sob meus cuidados médicos "
        f"nesta data, sendo constatada condição clínica que justifica seu "
        f"afastamento de suas atividades habituais por <b>{dias} dia(s)</b>, "
        f"a contar de {_data_extenso(data)}."
    )
    story.append(Paragraph(corpo, estilos["corpo"]))
    if cid:
        story.append(Paragraph(
            f"Classificação Internacional de Doenças (CID): <b>{_escape(cid)}</b>.",
            estilos["corpo"]))
    story.append(Paragraph(
        "Recomenda-se repouso e acompanhamento médico conforme orientação "
        "profissional.", estilos["corpo"]))
    story.append(Paragraph(
        "Por ser expressão da verdade, firmo o presente atestado para os fins "
        "que se fizerem necessários.", estilos["corpo"]))

    _rodape_assinatura(story, estilos, prof, data)
    doc.build(story)
    return buf.getvalue()
