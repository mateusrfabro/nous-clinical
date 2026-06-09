"""Utilitários de cor para o white-label (v2b): a clínica escolhe uma cor de
marca livre e derivamos o resto garantindo contraste WCAG AA.

Tudo server-side -> o CSS por clínica é servido por uma rota (text/css de
'self'), mantendo a CSP estrita (sem style inline).
"""

# Texto de referência: navy ink (claro) vs off-white (escuro).
_NAVY = (30, 41, 59)        # #1E293B
_OFFWHITE = (248, 250, 248)  # #F8FAF8
_WHITE = (255, 255, 255)


def hex_to_rgb(valor):
    """'#rrggbb' -> (r, g, b) ou None se inválido."""
    s = (valor or "").strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


def _srgb(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb):
    r, g, b = (_srgb(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def texto_sobre(rgb):
    """Cor de texto (navy ou off-white) com melhor contraste sobre `rgb`."""
    return "#1E293B" if _contraste(rgb, _NAVY) >= _contraste(rgb, _OFFWHITE) else "#F8FAF8"


def _escurecer(rgb, fator):
    return tuple(c * fator for c in rgb)


def cor_link(rgb):
    """Versão escurecida da cor que passa AA (>=4.5) como texto sobre branco."""
    cur, fator = rgb, 1.0
    while _contraste(cur, _WHITE) < 4.7 and fator > 0.2:
        fator -= 0.08
        cur = _escurecer(rgb, fator)
    return _hex(cur)


def css_para_cor(hex_cor):
    """Bloco CSS (string) que sobrescreve os tokens de PRIMÁRIA pra `hex_cor`.

    Escopado em body.app/body.public (vence a classe .tema-*). O accent
    continua vindo do tema escolhido. '' se a cor for inválida.
    """
    rgb = hex_to_rgb(hex_cor)
    if not rgb:
        return ""
    cor = _hex(rgb)
    return (
        "body.app, body.public {\n"
        f"  --brand-verde-claro: {cor};\n"
        f"  --primary-dark: {_hex(_escurecer(rgb, 0.84))};\n"
        f"  --primary-text: {cor_link(rgb)};\n"
        f"  --text-on-ouro: {texto_sobre(rgb)};\n"
        f"  --brand-primary-rgb: {rgb[0]}, {rgb[1]}, {rgb[2]};\n"
        "}\n"
    )
