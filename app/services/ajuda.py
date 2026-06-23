"""Nous Assistente — chatbot de AJUDA de uso do sistema (Claude API).

Responde "como faço X" usando EXCLUSIVAMENTE a base de ajuda em docs/ajuda/.
A chave da Anthropic fica só no servidor; nunca toca dado de paciente.

Modelo padrão: Claude Haiku 4.5 (barato; sem thinking/effort). Prompt caching:
o system (persona + base) é estável -> cache_control; o papel/clínica/pergunta
vão depois (em messages), pra não invalidar o cache.
"""
import logging
import re
from pathlib import Path

from flask import current_app

logger = logging.getLogger(__name__)

_DIR_AJUDA = Path(__file__).resolve().parents[2] / "docs" / "ajuda"
_PAPEIS_VALIDOS = {"recepcao", "admin", "profissional", "superadmin"}

# Persona + guardrails (estável -> entra no prefixo cacheado).
PERSONA = (
    "Você é o \"Nous Assistente\", um ajudante de USO do sistema Nous Clinical "
    "(software de gestão de clínica). Seu único trabalho é explicar COMO USAR o "
    "sistema, em português do Brasil.\n\n"
    "REGRAS (invioláveis):\n"
    "1. Responda SOMENTE sobre como usar o sistema, usando EXCLUSIVAMENTE a "
    "documentação fornecida abaixo. Se a resposta não estiver na documentação, "
    "diga que não sabe e sugira falar com o administrador da clínica. NÃO invente.\n"
    "2. Você NÃO dá orientação médica, diagnóstica ou de medicação. Se perguntarem "
    "isso, recuse educadamente: é fora do seu escopo.\n"
    "3. Você NÃO tem acesso a dados reais (pacientes, agenda, financeiro). Nunca "
    "invente nomes, CPFs, valores ou registros. Se pedirem 'quais consultas tem "
    "hoje', explique ONDE clicar para ver — você não consulta os dados.\n"
    "4. Respeite o PAPEL do usuário (informado no contexto). Não explique funções "
    "que o papel dele não acessa (ex.: prontuário para a recepção; relatórios para "
    "a recepção). Se perguntar algo fora do papel dele, diga que é de outro perfil.\n"
    "5. Se perguntarem de algo que o sistema não faz, diga que ainda não existe.\n"
    "6. Seja curto e direto. Use passos numerados quando fizer sentido."
)

_cache_base = {}   # papel -> texto da base; preenchido sob demanda


def _frontmatter_papeis(texto):
    """Lê 'papeis: [a, b]' do frontmatter YAML simples. None = todos."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", texto, re.DOTALL)
    if not m:
        return None, texto
    fm, corpo = m.group(1), texto[m.end():]
    pm = re.search(r"papeis:\s*\[([^\]]*)\]", fm)
    if not pm:
        return None, corpo
    papeis = {p.strip() for p in pm.group(1).split(",") if p.strip()}
    return (papeis or None), corpo


def _base_para_papel(papel):
    """Concatena os .md de ajuda relevantes ao papel (filtra por frontmatter).
    README é meta (como escrever) e fica de fora."""
    if papel in _cache_base:
        return _cache_base[papel]
    partes = []
    try:
        for arq in sorted(_DIR_AJUDA.glob("*.md")):
            if arq.name.lower() == "readme.md":
                continue
            texto = arq.read_text(encoding="utf-8")
            papeis, corpo = _frontmatter_papeis(texto)
            if papeis is None or papel in papeis:
                partes.append(corpo.strip())
    except OSError:
        logger.warning("AJUDA: não consegui ler docs/ajuda/", exc_info=True)
    base = "\n\n---\n\n".join(partes)
    _cache_base[papel] = base
    return base


def ia_disponivel():
    """Feature ligada E com chave configurada."""
    return bool(current_app.config.get("AJUDA_IA_ATIVA")
                and current_app.config.get("ANTHROPIC_API_KEY"))


def responder(pergunta, papel, clinica_nome=None, historico=None):
    """Pergunta -> (ok: bool, resposta: str). Best-effort: nunca levanta."""
    papel = papel if papel in _PAPEIS_VALIDOS else "recepcao"
    pergunta = (pergunta or "").strip()[:2000]
    if not pergunta:
        return False, "Faça uma pergunta sobre como usar o sistema."
    if not ia_disponivel():
        return False, ("O assistente de ajuda não está ativo nesta clínica. "
                       "Fale com o administrador.")

    base = _base_para_papel(papel)
    marca = (clinica_nome or "Nous Clinical").strip()[:80]
    contexto = (f"(Usuário com o papel: {papel}. O sistema pode estar com a marca "
                f"'{marca}'.)\n\nPergunta: {pergunta}")

    # Histórico curto (memória da sessão no browser) — opcional.
    mensagens = []
    for h in (historico or [])[-6:]:
        try:
            papel_msg = "user" if h.get("role") == "user" else "assistant"
            txt = str(h.get("content", "")).strip()[:1500]
            if txt:
                mensagens.append({"role": papel_msg, "content": txt})
        except (AttributeError, TypeError):
            continue
    mensagens.append({"role": "user", "content": contexto})

    try:
        import anthropic
        cliente = anthropic.Anthropic(
            api_key=current_app.config["ANTHROPIC_API_KEY"])
        resp = cliente.messages.create(
            model=current_app.config.get("MODEL_AJUDA", "claude-haiku-4-5"),
            max_tokens=600,
            system=[
                {"type": "text", "text": PERSONA},
                {"type": "text",
                 "text": "DOCUMENTAÇÃO DE AJUDA:\n\n" + base,
                 "cache_control": {"type": "ephemeral"}},
            ],
            messages=mensagens,
        )
        texto = next((b.text for b in resp.content if b.type == "text"), "")
        return True, (texto.strip() or "Não consegui responder. Tente reformular.")
    except Exception as exc:   # noqa: BLE001 — best-effort, não derruba o request
        logger.warning("AJUDA_FAIL: %s", exc.__class__.__name__, exc_info=True)
        return False, ("Não consegui responder agora. Tente de novo em instantes "
                       "ou fale com o administrador.")
