"""Gera o PDF imprimivel do Manual do Usuario a partir dos capitulos .md.

Converte os .md em HTML, monta um documento unico (capa + capitulos com quebra
de pagina) e renderiza para PDF via Chromium (Playwright). Imagens reais sao
carregadas via <base href> apontando para docs/manual/.

Uso:  python docs/manual/_build_pdf.py
Saida: docs/manual/Manual-Nous-Clinical.pdf
"""
import pathlib
import markdown

AQUI = pathlib.Path(__file__).resolve().parent
SAIDA = AQUI / "Manual-Nous-Clinical.pdf"

# Ordem do manual do CLIENTE (sem o capitulo 90, que e interno PGS).
CAPITULOS = [
    "00-bem-vindo", "01-painel", "02-agenda", "03-pacientes", "04-atendimento",
    "05-financeiro", "06-relatorios-auditoria", "07-crm", "08-cadastro-itens",
    "09-profissionais", "10-personalizacao", "11-whatsapp",
    "12-agendamento-online", "13-assistente-ia", "14-meu-perfil",
]

CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', 'Inter', Arial, sans-serif; color: #1E293B;
       font-size: 11.5pt; line-height: 1.55; }
h1 { color: #1E293B; font-size: 22pt; border-bottom: 3px solid #43B8A5;
     padding-bottom: 6px; margin-top: 0; }
h2 { color: #2A7F73; font-size: 15pt; margin-top: 1.4em; }
h3 { color: #2A7F73; font-size: 12.5pt; }
a { color: #2A7F73; text-decoration: none; }
code { background: #EDF2F1; padding: 1px 5px; border-radius: 4px;
       font-family: Consolas, monospace; font-size: 0.92em; }
img { max-width: 100%; height: auto; border: 1px solid #D7E0DE;
      border-radius: 8px; margin: 10px 0; box-shadow: 0 2px 8px rgba(30,41,59,.08); }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10.5pt; }
th, td { border: 1px solid #D7E0DE; padding: 6px 9px; text-align: left; }
th { background: #EDF2F1; }
blockquote { border-left: 4px solid #6FB59C; background: #F3F8F6;
             margin: 12px 0; padding: 8px 14px; border-radius: 0 8px 8px 0; }
blockquote p { margin: 4px 0; }
.capitulo { page-break-before: always; }
.capa { page-break-after: always; text-align: center; padding-top: 32vh; }
.capa .logo { font-size: 34pt; font-weight: 700; color: #1E293B; }
.capa .logo span { color: #43B8A5; }
.capa .tag { font-size: 15pt; color: #6FB59C; margin-top: 6px; font-style: italic; }
.capa .sub { font-size: 13pt; color: #475569; margin-top: 28px; }
.capa .rod { font-size: 10pt; color: #94A3B8; margin-top: 40px; }
"""

MD_EXT = ["tables", "fenced_code", "sane_lists", "nl2br"]


def main():
    capa = """
    <div class="capa">
      <div class="logo">Nous <span>Clinical</span></div>
      <div class="tag">Menos gestão. Mais medicina.</div>
      <div class="sub"><b>Manual do Usuário</b><br>Guia prático, tela por tela</div>
      <div class="rod">Documento gerado a partir do sistema · uso da equipe da clínica</div>
    </div>
    """
    partes = [capa]
    for nome in CAPITULOS:
        texto = (AQUI / f"{nome}.md").read_text(encoding="utf-8")
        html = markdown.markdown(texto, extensions=MD_EXT)
        partes.append(f'<section class="capitulo">{html}</section>')

    base = AQUI.as_uri() + "/"
    doc = f"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<base href="{base}"><style>{CSS}</style></head>
<body>{''.join(partes)}</body></html>"""

    html_tmp = AQUI / "_manual.html"
    html_tmp.write_text(doc, encoding="utf-8")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(html_tmp.as_uri(), wait_until="networkidle")
        pg.pdf(path=str(SAIDA), format="A4", print_background=True,
               margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        b.close()
    html_tmp.unlink(missing_ok=True)
    print(f"PDF gerado: {SAIDA}  ({SAIDA.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
