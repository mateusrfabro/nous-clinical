"""Converte UM arquivo .md em PDF (mesma identidade visual do manual).

Uso:  python docs/manual/_build_doc_pdf.py <caminho.md> [saida.pdf]
"""
import sys
import pathlib
import markdown

AQUI = pathlib.Path(__file__).resolve().parent

# Reaproveita o CSS do manual.
CSS = (AQUI / "_build_pdf.py").read_text(encoding="utf-8")
CSS = CSS.split('CSS = """', 1)[1].split('"""', 1)[0]

MD_EXT = ["tables", "fenced_code", "sane_lists", "nl2br"]


def main():
    if len(sys.argv) < 2:
        print("uso: _build_doc_pdf.py <arquivo.md> [saida.pdf]")
        return
    src = pathlib.Path(sys.argv[1]).resolve()
    out = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 \
        else src.with_suffix(".pdf")
    html = markdown.markdown(src.read_text(encoding="utf-8"), extensions=MD_EXT)
    base = src.parent.as_uri() + "/"
    doc = f"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<base href="{base}"><style>{CSS}</style></head><body>{html}</body></html>"""
    tmp = src.with_name("_tmp_doc.html")
    tmp.write_text(doc, encoding="utf-8")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(tmp.as_uri(), wait_until="networkidle")
        pg.pdf(path=str(out), format="A4", print_background=True,
               margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        b.close()
    tmp.unlink(missing_ok=True)
    print(f"PDF gerado: {out}  ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
