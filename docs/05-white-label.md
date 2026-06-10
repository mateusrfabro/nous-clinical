# 5. White-label (identidade por clínica)

Cada clínica pode ter a **própria marca**: tema/cor, logo, e um **portal público
por slug** (`/c/<slug>`) com login e agendamento brandados. Quem configura é o
**admin da clínica** (self-service), na tela **Aparência**
(`/configuracoes/aparencia`). A Nous (superadmin) só provisiona a clínica.

## Arquitetura de design tokens (3 camadas)
Tudo vive em `app/static/css/style.css` no bloco `:root`:
1. **Primitivo** — `--brand-primary-rgb`, `--brand-accent-rgb` (alimentam os
   `rgba()` dinâmicos: glow, tints, hovers). **Todos os `rgba()` de marca usam
   essas vars** (não há mais hex de marca hardcoded).
2. **Semântico** — `--brand-verde-claro` (primária), `--brand-ouro` (accent),
   `--primary`, `--text-on-ouro` (texto sobre a primária), etc.
3. **Por tenant** — uma classe no `<body>` sobrescreve só a camada de marca.

## (a) Temas curados — classe no `<body>`
6 temas (`teal, indigo, violeta, verde, ambar, petroleo`) definidos como
`.tema-<nome> { ... }` em `style.css`. O `<body>` recebe `class="app tema-<x>"`
(ou `public tema-<x>`), e como todo o CSS referencia os tokens, a UI inteira
recolore. **Contraste WCAG AA garantido por tema** (o `--text-on-ouro` vira navy
ou off-white conforme a primária).

## (b) Cor livre — rota `/tema.css`
Cor arbitrária não cabe numa classe pré-definida, então é servida por uma **rota
que devolve `text/css`** (de `'self'` → CSP-safe). `app/services/cores.py`
(`css_para_cor`) calcula os derivados a partir da cor escolhida com **contraste
WCAG real**: `primary-dark`, `primary-text` (link AA sobre branco) e
`text-on-ouro` (navy/off-white). A cor sobrescreve **só a primária**; o accent
continua vindo do tema.
- Autenticado: `configuracoes.tema_css`. Portal público: `portal.tema_css`.
- O `<link>` no `<head>` só entra quando há `cor_primaria` (var `tema_css_url`).

## (c) Logo — upload self-service
`Clinica.logo_key`/`logo_mime`. Upload em `configuracoes.logo_upload`
(**PNG/JPG/WEBP; SVG bloqueado — anti-XSS**; content-type derivado da extensão
validada, nunca do cliente). Guardado no `storage` (fora de `static/`). Servido
por rota — autenticada (`configuracoes.logo_servir`, isolada por clínica) ou
pública (`portal.logo`). O macro `brand()` em `base.html` mostra a logo no lugar
do wordmark Nous quando existe.

## (d) Portal público por clínica — `/c/<slug>`
`app/routes/portal.py`. Resolve a clínica pelo `slug` (404 se inexistente/inativa),
marca **`g.portal_clinica`** (o context processor usa pra brandar a página
pública) e **delega** pra lógica existente — sem duplicar segurança:
| Rota | O que faz |
|---|---|
| `/c/<slug>` | login **com a marca da clínica** (reusa `auth.login`) |
| `/c/<slug>/agendar` | agendamento online **escopado** aos profissionais da clínica (reusa `agenda.agendar_online`) |
| `/c/<slug>/logo` | logo pública |
| `/c/<slug>/tema.css` | CSS da cor livre, público |
| `/c/<slug>/favicon.svg` | favicon da clínica, público |

> **Multi-tenant no público:** rota pública tem `g.clinica_id = None` (sem escopo).
> Por isso `agendar_online` resolve a clínica via `_portal_clinica()` (slug ou
> clínica única) e **filtra os profissionais manualmente**; em multi-clínica sem
> slug, **redireciona** em vez de listar todo mundo (não faz "pooling").

## (e) Favicon por clínica
`cores.svg_favicon(letra, cor)` gera um SVG (quadrado na cor de marca + inicial,
texto em contraste). Rotas: `portal.favicon` (público) e `configuracoes.favicon`
(autenticado). Plataforma usa `app/static/favicon.svg`. O `<link rel="icon">` em
`base.html` aponta pra `favicon_url` (escolhido no context processor).

## (f) Slug + link + QR (na tela Aparência)
O admin define o **slug** (`configuracoes.slug_salvar`, normalizado e **único**),
e ganha o link `/c/<slug>/agendar` (botão Copiar via `copiar.js`) + **QR Code**
SVG (`configuracoes.qr_agendamento`, gerado com **segno**, baixável). A clínica
usa o link/QR onde quiser (Instagram, WhatsApp, impresso na recepção) — **não há
integração com redes sociais**, é só o ativo gerado.

## Como o branding chega no template
Tudo via **context processor** em `app/__init__.py` (um único lookup da clínica):
expõe `tema_clinica` (classe do body), `clinica_logo_url`, `tema_css_url`,
`favicon_url`, `portal_clinica`. Logado → clínica do usuário; público no portal →
`g.portal_clinica`.

## Regras ao mexer aqui
- **Nunca** `style=` inline pra cor — use a classe `.tema-*` ou a rota `/tema.css`.
- Preview ao vivo (color picker) usa `el.style.setProperty` no JS (`tema-cor.js`)
  — CSSOM é permitido pela CSP; espelhe o cálculo de contraste do servidor.
- Logo: só raster. Se um dia aceitar SVG, **sanitize** (XSS).
