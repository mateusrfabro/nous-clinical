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
    assert "Agendar demonstração" not in body   # sem contato, CTA de demo não aparece


def test_produto_alias_renderiza_a_landing(client):
    """Alias estável /produto p/ o comercial compartilhar — mesma landing."""
    r = client.get("/produto")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Menos gestão" in body and "modulos" in body
    # Canonical aponta pra raiz (evita conteúdo duplicado).
    assert 'rel="canonical"' in body and body.rstrip().endswith("</html>")


def test_modulos_detalhe_recolhivel(client):
    """U2: cada card de módulo enxuga a densidade num <details> nativo (o texto
    segue no HTML — bom p/ SEO — só recolhido por padrão)."""
    body = client.get("/").get_data(as_text=True)
    assert "lp-card-more" in body and "Ver detalhes" in body
    # o detalhe do card continua presente no HTML (não foi removido)
    assert "Kanban" in body and "conciliação do extrato" in body


def test_cta_usa_contato_comercial_quando_configurado(app, client):
    app.config["CONTATO_COMERCIAL"] = "https://wa.me/5543999999999"
    try:
        body = client.get("/").get_data(as_text=True)
        assert "Agendar demonstração" in body   # CTA de demo aparece
        assert "wa.me/5543999999999" in body     # aponta pro WhatsApp configurado
    finally:
        app.config["CONTATO_COMERCIAL"] = ""
