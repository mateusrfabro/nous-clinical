"""Fundação de SEO: robots.txt, sitemap.xml, canonical, Open Graph e JSON-LD.

Garante que o marketing é indexável, as áreas logadas ficam fora do crawl, e
que só clínicas que optaram por ser públicas entram no sitemap (privacidade)."""
import json
import re


def _ld_json(body):
    """Extrai e faz parse do bloco JSON-LD da página (falha se inválido)."""
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>',
                  body, re.S)
    assert m, "JSON-LD não encontrado na landing"
    return json.loads(m.group(1))


# ---------------------------------------------------------------- robots.txt --
def test_robots_txt_publico_e_bloqueia_areas_logadas(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert r.mimetype == "text/plain"
    body = r.get_data(as_text=True)
    assert "User-agent: *" in body
    # Áreas logadas bloqueadas (defesa em profundidade).
    for area in ("/painel", "/financeiro", "/pacientes", "/auditoria",
                 "/agenda/", "/redefinir-senha"):
        assert f"Disallow: {area}" in body
    # Aponta o sitemap.
    assert "Sitemap:" in body and "/sitemap.xml" in body


def test_robots_nao_bloqueia_agendar_publico(client):
    """`/agendar` (portal público) não pode ser pego pela regra de `/agenda/`."""
    body = client.get("/robots.txt").get_data(as_text=True)
    assert "Disallow: /agendar" not in body


# --------------------------------------------------------------- sitemap.xml --
def test_sitemap_tem_raiz_e_portal_da_clinica_ativa(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert "xml" in r.mimetype
    body = r.get_data(as_text=True)
    assert "<urlset" in body and "</urlset>" in body
    assert "<loc>" in body
    # A clínica do seed tem agendamento online ligado -> portal indexável.
    assert "/c/teste</loc>" in body


def test_sitemap_exclui_clinica_sem_agendamento_online(app, client):
    """Clínica que NÃO optou por agendamento público não vaza no sitemap."""
    from app import db
    from app.models import Clinica
    with app.app_context():
        db.session.add(Clinica(nome="Oculta", slug="oculta",
                               agendamento_online_ativo=False))
        db.session.commit()
    body = client.get("/sitemap.xml").get_data(as_text=True)
    assert "/c/teste</loc>" in body      # a ativa entra
    assert "/c/oculta" not in body       # a inativa não


# ------------------------------------------------ canonical / Open Graph / LD --
def test_landing_tem_canonical_og_e_twitter(client):
    body = client.get("/").get_data(as_text=True)
    assert 'rel="canonical"' in body
    assert 'property="og:type" content="website"' in body
    assert 'property="og:title"' in body
    assert 'property="og:image"' in body
    assert 'name="twitter:card" content="summary_large_image"' in body


def test_landing_json_ld_valido_org_software_faq(client):
    """O JSON-LD tem que ser JSON válido e descrever a entidade, o software e a
    FAQ — é o que alimenta rich results e AI Overviews."""
    body = client.get("/").get_data(as_text=True)
    data = _ld_json(body)
    tipos = {node["@type"] for node in data["@graph"]}
    assert {"Organization", "SoftwareApplication", "FAQPage"} <= tipos
    # A FAQPage precisa das perguntas (não pode ser um esqueleto vazio).
    faq = next(n for n in data["@graph"] if n["@type"] == "FAQPage")
    assert len(faq["mainEntity"]) == 6


def test_paginas_internas_herdam_canonical_e_og(client):
    """base.html dá canonical + OG a toda página (não só à landing)."""
    body = client.get("/login").get_data(as_text=True)
    assert 'rel="canonical"' in body
    assert 'property="og:title"' in body
