"""Landing comercial pública (/) — estrutura, honestidade e CTA configurável."""


def test_landing_anonima_tem_secoes(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    for marca in ("modulos", "Diferenciais", "lp-trust", "lp-cta",
                  "Menos gestão", "Mais medicina"):
        assert marca in body


def test_landing_honesta_nfse_roadmap_whatsapp_opcional(client):
    """O material não pode prometer NFS-e como pronta nem WhatsApp como incluído."""
    body = client.get("/").get_data(as_text=True)
    assert "roadmap" in body and "certificado digital A1" in body
    assert "opcional" in body and "pagas pela clínica" in body


def test_cta_padrao_cai_no_login(client):
    """Sem CONTATO_COMERCIAL configurado, o CTA aponta pro login (não inventa canal)."""
    body = client.get("/").get_data(as_text=True)
    assert "Entrar na plataforma" in body
    assert "Falar com a gente" not in body


def test_cta_usa_contato_comercial_quando_configurado(app, client):
    app.config["CONTATO_COMERCIAL"] = "https://wa.me/5543999999999"
    try:
        body = client.get("/").get_data(as_text=True)
        assert "Falar com a gente" in body
        assert "wa.me/5543999999999" in body
    finally:
        app.config["CONTATO_COMERCIAL"] = ""
