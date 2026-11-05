"""Captura de telas (prints reais) para o Manual do Usuario.

Sobe um browser (Playwright/Chromium), loga com cada papel e tira screenshot
de cada tela-alvo, salvando em docs/manual/assets/. Pressupoe o app rodando em
http://127.0.0.1:5060 com WHATSAPP_ATIVO=true e o seed + seed_whatsapp_demo.

Uso:  python docs/manual/_capture.py
"""
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
os.environ.setdefault("WHATSAPP_ATIVO", "true")

from playwright.sync_api import sync_playwright  # noqa: E402

BASE = "http://127.0.0.1:5060"
ASSETS = pathlib.Path(__file__).resolve().parent / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

SENHA = "demo123"


def garantir_superadmin():
    """Cria um superadmin (sem clinica) para capturar a tela de Clinicas."""
    from app import create_app, db
    from app.models import Usuario
    from app.services.passwords import hash_senha
    from datetime import datetime, timezone
    app = create_app("development")
    with app.app_context():
        if not db.session.query(Usuario).filter_by(email="super@nous.com").first():
            db.session.add(Usuario(
                email="super@nous.com", senha_hash=hash_senha(SENHA),
                nome_responsavel="Super Admin", telefone="(43) 90000-0000",
                tipo="superadmin", aceite_termos_em=datetime.now(timezone.utc)))
            db.session.commit()
            print("superadmin criado")


# (nome do arquivo, caminho) por papel
ALVOS = {
    "admin@nous.com": [
        ("01-painel", "/painel"),
        ("agenda-dia", "/agenda/"),
        ("agenda-semana", "/agenda/semana"),
        ("agenda-grade", "/agenda/grade"),
        ("agenda-novo", "/agenda/novo"),
        ("agenda-bloqueios", "/agenda/bloqueios"),
        ("pacientes-lista", "/pacientes/"),
        ("pacientes-novo", "/pacientes/novo"),
        ("paciente-detalhe", "/pacientes/1"),
        ("profissionais-lista", "/profissionais/"),
        ("profissional-novo", "/profissionais/novo"),
        ("financeiro-fluxo", "/financeiro/"),
        ("financeiro-novo", "/financeiro/novo"),
        ("financeiro-contas", "/financeiro/contas"),
        ("relatorios-index", "/relatorios/"),
        ("relatorios-visaogeral", "/relatorios/?gerar=1&tipo=visao_geral"),
        ("auditoria", "/auditoria/"),
        ("config-aparencia", "/configuracoes/aparencia"),
        ("procedimentos", "/procedimentos/"),
        ("crm-retornos", "/crm/retornos"),
        ("crm-aniversariantes", "/crm/aniversariantes"),
        ("whatsapp-inbox", "/whatsapp/"),
        ("whatsapp-conversa", "/whatsapp/1"),
        ("whatsapp-config", "/whatsapp/config"),
        ("perfil", "/perfil/"),
    ],
    "dra.ana@nous.com": [
        ("prof-painel", "/painel"),
        ("prof-agenda", "/agenda/"),
        ("prof-atendimento", "/agenda/1/atendimento"),
        ("prof-paciente-detalhe", "/pacientes/1"),
    ],
    "recepcao@nous.com": [
        ("recepcao-painel", "/painel"),
        ("recepcao-financeiro", "/financeiro/"),
    ],
    "super@nous.com": [
        ("superadmin-clinicas", "/clinicas/"),
    ],
}

PUBLICAS = [
    ("00-login", "/login"),
    ("agendamento-online", "/c/nous/agendar"),
]


def login(page, email):
    page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    page.fill("input[name=email]", email)
    page.fill("input[name=senha]", SENHA)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")


def snap(page, nome):
    try:
        page.wait_for_timeout(600)  # deixa fontes/transicoes assentarem
        page.screenshot(path=str(ASSETS / f"{nome}.png"), full_page=True)
        print(f"  ok  {nome}")
    except Exception as e:  # noqa: BLE001
        print(f"  ERRO {nome}: {e}")


def main():
    garantir_superadmin()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--explicitly-allowed-ports=5060"])
        # Publicas (sem login)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900},
                                  device_scale_factor=2)
        pg = ctx.new_page()
        for nome, url in PUBLICAS:
            pg.goto(f"{BASE}{url}", wait_until="networkidle")
            snap(pg, nome)
        ctx.close()

        for email, alvos in ALVOS.items():
            ctx = browser.new_context(viewport={"width": 1366, "height": 900},
                                      device_scale_factor=2)
            pg = ctx.new_page()
            try:
                login(pg, email)
            except Exception as e:  # noqa: BLE001
                print(f"LOGIN FALHOU {email}: {e}")
                ctx.close()
                continue
            print(f"[{email}]")
            for nome, url in alvos:
                try:
                    pg.goto(f"{BASE}{url}", wait_until="networkidle")
                except Exception as e:  # noqa: BLE001
                    print(f"  ERRO goto {nome}: {e}")
                    continue
                snap(pg, nome)
            ctx.close()
        browser.close()
    print("FIM")


if __name__ == "__main__":
    main()
