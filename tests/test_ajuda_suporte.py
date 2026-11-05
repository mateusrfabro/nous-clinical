"""Suporte de ajuda LOCAL (custo zero) — busca na base docs/ajuda/ SEM IA/API.

Garante que o widget responde de graça, respeita o papel e nunca depende de chave.
"""
from app.services.ajuda import buscar_local, sugestoes


def test_busca_encontra_resposta_relevante():
    ok, resp, fonte = buscar_local("como agendar uma consulta", "recepcao")
    assert ok is True
    assert resp and len(resp) > 10
    assert fonte  # título da seção que casou


def test_busca_pergunta_vazia_orienta_sem_quebrar():
    ok, resp, fonte = buscar_local("   ", "recepcao")
    assert ok is False
    assert fonte is None
    assert resp  # mensagem de orientação


def test_busca_sem_correspondencia_falha_limpo():
    ok, _, fonte = buscar_local("xyzzy qwerty zzz coisa inexistente", "recepcao")
    assert ok is False
    assert fonte is None


def test_isolamento_por_papel_prontuario():
    # "prescrição"/"evolução" só existem no doc de atendimento (profissional/admin).
    # A recepção NÃO pode receber esse conteúdo (LGPD).
    ok_prof, _, _ = buscar_local("prescrição e evolução", "profissional")
    ok_rec, _, _ = buscar_local("prescrição e evolução", "recepcao")
    assert ok_prof is True
    assert ok_rec is False


def test_sugestoes_nao_vazio_e_strings():
    s = sugestoes("recepcao")
    assert isinstance(s, list) and len(s) >= 1
    assert all(isinstance(x, str) and x for x in s)


def test_rota_buscar_funciona_sem_chave_anthropic(client_recepcao, app):
    # Sem ANTHROPIC_API_KEY -> prova que o suporte NÃO usa IA (custo zero).
    app.config["ANTHROPIC_API_KEY"] = ""
    r = client_recepcao.post("/ajuda/buscar",
                             json={"pergunta": "como recebo o pagamento da consulta"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert d["resposta"]


def test_rota_buscar_exige_login(client):
    r = client.post("/ajuda/buscar", json={"pergunta": "x"})
    assert r.status_code in (302, 401)
