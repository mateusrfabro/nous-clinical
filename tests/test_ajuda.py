"""Chatbot de ajuda ("Nous Assistente"): gate, flag on/off, auditoria,
filtro por papel da base. NÃO chama a Claude API (responder é mockado)."""
from app.models import AuditLog


def test_base_de_ajuda_filtra_por_papel(app):
    """Recepção não recebe a doc de prontuário (LGPD); profissional sim."""
    with app.app_context():
        from app.services.ajuda import _base_para_papel
        assert "Prontuário" not in _base_para_papel("recepcao")
        assert "Prontuário" in _base_para_papel("profissional")


def test_widget_oculto_quando_desligado(client_admin):
    # AJUDA_IA_ATIVA é False por padrão -> widget não aparece.
    r = client_admin.get("/agenda/")
    assert r.status_code == 200
    assert b"ajuda-wrap" not in r.data


def test_chat_desligado_responde_inativo(client_admin):
    r = client_admin.post("/ajuda/chat", json={"pergunta": "como agendo?"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is False
    assert "ativo" in d["resposta"].lower()


def test_chat_exige_login(client):
    r = client.post("/ajuda/chat", json={"pergunta": "oi"})
    assert r.status_code in (301, 302)            # login_required


def test_chat_resposta_e_auditoria(app, client_admin, monkeypatch):
    app.config["AJUDA_IA_ATIVA"] = True
    app.config["ANTHROPIC_API_KEY"] = "chave-de-teste"
    import app.routes.ajuda as rota
    monkeypatch.setattr(rota, "responder",
                        lambda *a, **k: (True, "Clique em + Agendar consulta."))
    antes = AuditLog.query.filter_by(acao="ajuda_consulta").count()

    r = client_admin.post("/ajuda/chat", json={"pergunta": "como agendo?"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True and "Agendar" in d["resposta"]
    # auditou (só metadado), sem o texto da pergunta
    log = AuditLog.query.filter_by(acao="ajuda_consulta").order_by(
        AuditLog.id.desc()).first()
    assert AuditLog.query.filter_by(acao="ajuda_consulta").count() == antes + 1
    assert "como agendo" not in (log.detalhes or "")   # não loga PII/pergunta

    app.config["AJUDA_IA_ATIVA"] = False              # restaura p/ outros testes


def test_widget_aparece_quando_ativo(app, client_admin):
    app.config["AJUDA_IA_ATIVA"] = True
    app.config["ANTHROPIC_API_KEY"] = "x"
    try:
        r = client_admin.get("/agenda/")
        assert b"ajuda-wrap" in r.data and b"ajuda-widget.js" in r.data
    finally:
        app.config["AJUDA_IA_ATIVA"] = False
