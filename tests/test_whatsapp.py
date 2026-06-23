"""WhatsApp Business (Cloud API) — webhook multi-tenant, inbox, config, cripto.

Não chama a Meta de verdade (envio é testado pelo caminho 'conta inativa', que
nem tenta rede). Cobre: handshake, assinatura, roteamento por phone_number_id,
casamento de paciente, gates de papel, feature off, e cifragem do token.
"""
import hashlib
import hmac
import json

from app.models import (Clinica, WhatsAppConta, WhatsAppContato,
                        WhatsAppMensagem)
from app import db


# ----------------------------- helpers --------------------------------------
def _clinica_id():
    return Clinica.query.first().id


def _cria_conta(clinica_id, pnid, ativo=True, token="tok-xyz"):
    from app.services.cripto import cifrar
    conta = WhatsAppConta(clinica_id=clinica_id, phone_number_id=pnid,
                          ativo=ativo, token_cifrado=cifrar(token))
    db.session.add(conta)
    db.session.commit()
    return conta


def _payload(pnid, wa_id, texto, wamid="wamid.AAA", nome="Fulano"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "550000", "phone_number_id": pnid},
            "contacts": [{"profile": {"name": nome}, "wa_id": wa_id}],
            "messages": [{"from": wa_id, "id": wamid, "timestamp": "1",
                          "type": "text", "text": {"body": texto}}],
        }}]}],
    }


def _liga(app):
    app.config["WHATSAPP_ATIVO"] = True


# ----------------------------- cripto ---------------------------------------
def test_cripto_round_trip(app):
    with app.app_context():
        from app.services.cripto import cifrar, decifrar
        cif = cifrar("token-secreto-123")
        assert cif and cif != "token-secreto-123"      # não fica em claro
        assert decifrar(cif) == "token-secreto-123"
        assert decifrar(None) is None
        assert decifrar("lixo-nao-decifravel") is None  # não levanta


# ----------------------------- webhook --------------------------------------
def test_webhook_handshake_ok_e_token_errado(client, app):
    tok = app.config["WHATSAPP_VERIFY_TOKEN"]
    r = client.get(f"/whatsapp/webhook?hub.mode=subscribe&hub.verify_token={tok}"
                   "&hub.challenge=12345")
    assert r.status_code == 200 and r.data == b"12345"

    r2 = client.get("/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=errado"
                    "&hub.challenge=12345")
    assert r2.status_code == 403


def test_webhook_processa_mensagem_e_casa_paciente(client, app):
    with app.app_context():
        cid = _clinica_id()
        _cria_conta(cid, "PN_AAA")

    # O paciente do seed tem telefone (43) 98888-0000 -> wa_id 5543988880000.
    r = client.post("/whatsapp/webhook",
                    json=_payload("PN_AAA", "5543988880000", "Olá, tudo bem?"))
    assert r.status_code == 200

    with app.app_context():
        contato = WhatsAppContato.query.filter_by(wa_id="5543988880000").first()
        assert contato is not None
        assert contato.clinica_id == _clinica_id()
        assert contato.paciente_id is not None        # casou pelo telefone
        assert contato.nao_lidas == 1
        msgs = WhatsAppMensagem.query.filter_by(contato_id=contato.id).all()
        assert len(msgs) == 1
        assert msgs[0].direcao == "in" and msgs[0].texto == "Olá, tudo bem?"


def test_webhook_dedupe_nao_duplica(client, app):
    with app.app_context():
        _cria_conta(_clinica_id(), "PN_DUP")
    p = _payload("PN_DUP", "5511999990000", "oi", wamid="wamid.SAME")
    client.post("/whatsapp/webhook", json=p)
    client.post("/whatsapp/webhook", json=p)        # reentrega do mesmo id
    with app.app_context():
        assert WhatsAppMensagem.query.filter_by(wa_message_id="wamid.SAME").count() == 1


def test_webhook_conta_desconhecida_ignora(client, app):
    # phone_number_id sem conta -> no-op, mas responde 200 (senão Meta re-tenta).
    r = client.post("/whatsapp/webhook",
                    json=_payload("PN_INEXISTENTE", "5511888880000", "x"))
    assert r.status_code == 200
    with app.app_context():
        assert WhatsAppContato.query.filter_by(wa_id="5511888880000").first() is None


def test_webhook_assinatura(client, app):
    app.config["WHATSAPP_APP_SECRET"] = "segredo-app"
    with app.app_context():
        _cria_conta(_clinica_id(), "PN_SIG")
    corpo = json.dumps(_payload("PN_SIG", "5511777770000", "assinado")).encode()

    # Assinatura errada -> 403.
    r_bad = client.post("/whatsapp/webhook", data=corpo,
                        content_type="application/json",
                        headers={"X-Hub-Signature-256": "sha256=deadbeef"})
    assert r_bad.status_code == 403

    # Assinatura correta -> 200.
    sig = hmac.new(b"segredo-app", corpo, hashlib.sha256).hexdigest()
    r_ok = client.post("/whatsapp/webhook", data=corpo,
                       content_type="application/json",
                       headers={"X-Hub-Signature-256": f"sha256={sig}"})
    assert r_ok.status_code == 200
    app.config["WHATSAPP_APP_SECRET"] = ""


def test_webhook_roteia_por_phone_number_id(client, app):
    """Duas clínicas, dois números: a mensagem cai na clínica DONA do número."""
    with app.app_context():
        cid_a = _clinica_id()
        outra = Clinica(nome="Clínica B", slug="b")
        db.session.add(outra)
        db.session.commit()
        cid_b = outra.id
        _cria_conta(cid_a, "PN_A")
        _cria_conta(cid_b, "PN_B")

    client.post("/whatsapp/webhook", json=_payload("PN_B", "5511555550000", "pra B"))
    with app.app_context():
        contato = WhatsAppContato.query.filter_by(wa_id="5511555550000").first()
        assert contato is not None and contato.clinica_id == cid_b   # não a A


# ----------------------------- inbox / gates --------------------------------
def test_inbox_feature_off_404(client_admin):
    # WHATSAPP_ATIVO é False por padrão -> rota inerte.
    assert client_admin.get("/whatsapp/").status_code == 404


def test_inbox_ativo_admin_ok(client_admin, app):
    _liga(app)
    try:
        assert client_admin.get("/whatsapp/").status_code == 200
    finally:
        app.config["WHATSAPP_ATIVO"] = False


def test_inbox_bloqueia_profissional(client_prof, app):
    _liga(app)
    try:
        # role_required redireciona (302) quem não tem papel; nunca 200.
        assert client_prof.get("/whatsapp/").status_code in (302, 403)
    finally:
        app.config["WHATSAPP_ATIVO"] = False


def test_config_so_admin(client_recepcao, client_admin, app):
    _liga(app)
    try:
        assert client_recepcao.get("/whatsapp/config").status_code in (302, 403)
        assert client_admin.get("/whatsapp/config").status_code == 200
    finally:
        app.config["WHATSAPP_ATIVO"] = False


def test_config_salva_token_cifrado(client_admin, app):
    _liga(app)
    try:
        r = client_admin.post("/whatsapp/config", data={
            "phone_number_id": "109998887776665", "token": "token-super-secreto",
            "ativo": "on"}, follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            from app.services.cripto import decifrar
            conta = WhatsAppConta.query.filter_by(phone_number_id="109998887776665").first()
            assert conta is not None and conta.ativo is True
            assert conta.token_cifrado and "token-super-secreto" not in conta.token_cifrado
            assert decifrar(conta.token_cifrado) == "token-super-secreto"
    finally:
        app.config["WHATSAPP_ATIVO"] = False


def test_inbox_isolada_entre_clinicas(client_admin, app):
    """Admin da Clínica A NÃO vê conversa da Clínica B (cross-tenant)."""
    _liga(app)
    try:
        with app.app_context():
            outra = Clinica(nome="Clínica B iso", slug="b-iso")
            db.session.add(outra)
            db.session.commit()
            db.session.add(WhatsAppContato(
                clinica_id=outra.id, wa_id="5511222220000", nome="De Outra"))
            db.session.commit()
        r = client_admin.get("/whatsapp/")
        assert r.status_code == 200
        assert b"5511222220000" not in r.data and "De Outra".encode() not in r.data
    finally:
        app.config["WHATSAPP_ATIVO"] = False


def test_webhook_atualiza_status_de_envio(client, app):
    with app.app_context():
        cid = _clinica_id()
        _cria_conta(cid, "PN_ST")
        contato = WhatsAppContato(clinica_id=cid, wa_id="5511333330000")
        db.session.add(contato)
        db.session.flush()
        db.session.add(WhatsAppMensagem(
            clinica_id=cid, contato_id=contato.id, direcao="out",
            wa_message_id="wamid.OUT1", texto="oi", status="enviada"))
        db.session.commit()
    payload = {"object": "whatsapp_business_account", "entry": [{"id": "W",
        "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"phone_number_id": "PN_ST"},
            "statuses": [{"id": "wamid.OUT1", "status": "read"}]}}]}]}
    client.post("/whatsapp/webhook", json=payload)
    with app.app_context():
        m = WhatsAppMensagem.query.filter_by(wa_message_id="wamid.OUT1").first()
        assert m.status == "lida"


def test_webhook_mensagem_nao_texto(client, app):
    with app.app_context():
        _cria_conta(_clinica_id(), "PN_IMG")
    payload = {"object": "whatsapp_business_account", "entry": [{"id": "W",
        "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"phone_number_id": "PN_IMG"},
            "contacts": [{"profile": {"name": "Foto"}, "wa_id": "5511666660000"}],
            "messages": [{"from": "5511666660000", "id": "wamid.IMG",
                          "type": "image", "image": {"id": "x"}}]}}]}]}
    client.post("/whatsapp/webhook", json=payload)
    with app.app_context():
        m = WhatsAppMensagem.query.filter_by(wa_message_id="wamid.IMG").first()
        assert m is not None and m.texto == "[image]"


def test_normaliza_br():
    from app.services.whatsapp import normaliza_br
    assert normaliza_br("(43) 98888-0000") == "5543988880000"
    assert normaliza_br("5543988880000") == "5543988880000"
    assert normaliza_br("4332220000") == "554332220000"   # fixo 10 dígitos
    assert normaliza_br("") is None
    assert normaliza_br(None) is None


def test_webhook_payload_malformado_nao_quebra(client, app):
    # Sem entry/changes/value -> no-op, responde 200 (best-effort).
    assert client.post("/whatsapp/webhook", json={}).status_code == 200
    assert client.post("/whatsapp/webhook", json={"entry": [{}]}).status_code == 200


def test_enviar_conta_inativa_nao_envia(client_admin, app):
    _liga(app)
    try:
        with app.app_context():
            cid = _clinica_id()
            _cria_conta(cid, "PN_OFF", ativo=False)
            contato = WhatsAppContato(clinica_id=cid, wa_id="5511444440000",
                                      nome="X")
            db.session.add(contato)
            db.session.commit()
            contato_id = contato.id
        r = client_admin.post(f"/whatsapp/{contato_id}/enviar",
                              data={"texto": "oi"}, follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            saida = WhatsAppMensagem.query.filter_by(
                contato_id=contato_id, direcao="out").count()
            assert saida == 0          # conta inativa -> não cria msg de saída
    finally:
        app.config["WHATSAPP_ATIVO"] = False
