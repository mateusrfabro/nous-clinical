# 6. Deploy

> Hoje o produto roda em **dev** (SQLite + `python run.py`) e é exposto pra demo
> via **Cloudflare Tunnel**. A infra de produção (Postgres + gunicorn) está
> **pronta no repositório** (Docker), mas ainda não há hospedagem fixa contratada.

## Artefatos de produção (já no repo)
- **`Dockerfile`** — imagem da app.
- **`docker-compose.yml`** — Postgres + Redis + app (gunicorn).
- **`entrypoint.sh`** — aplica migrations e sobe o gunicorn.
- **`gunicorn`** em `requirements.txt`.

## Subir com Docker (produção)
```bash
cp .env.example .env       # defina SECRET_KEY, DATABASE_URL, SMTP_*, etc.
docker compose up -d --build
# entrypoint.sh roda `flask db upgrade` e inicia o gunicorn
```
**Nunca** rode `python run.py` em produção (debugger do Werkzeug = RCE). Em prod,
`FLASK_ENV=production` faz o app:
- exigir `SECRET_KEY` (boot falha sem ela),
- ligar `ProxyFix`, `force_https`, HSTS, cookies `Secure`,
- desligar o debug.

## Checklist de produção
- [ ] `SECRET_KEY` forte e secreta (não a de dev).
- [ ] `DATABASE_URL` apontando pro Postgres; `flask db upgrade` aplicado.
- [ ] `PUBLIC_BASE_URL` = domínio real (links de confirmação/lembrete/portal).
- [ ] SMTP/Telegram configurados (ou aceitar que notificações são best-effort).
- [ ] `TAREFAS_TOKEN` setado + agendador chamando `/tarefas/lembretes` (ou `flask lembretes` via cron).
- [ ] Backups do Postgres + do diretório de `storage` (uploads/exames — dado LGPD).
- [ ] Logs sem PII (já há filtro que redige tokens; `services/pii.py` mascara e-mails).
- [ ] HTTPS no domínio (Cloudflare/Caddy/Nginx na frente do gunicorn).

## Demo via Cloudflare Tunnel (efêmero)
Quick tunnel **sem conta** — URL aleatória a cada processo, **sem garantia de
uptime** (cai quando a rede oscila). Procedimento usado:
```bash
cloudflared tunnel --url http://localhost:5050 --protocol http2
# pega a URL https://<random>.trycloudflare.com do log
```
- `--protocol http2` evita o timeout de QUIC quando UDP está bloqueado.
- Se a máquina usa **Tailscale** com "Use Tailscale DNS", o domínio do túnel pode
  não resolver no navegador → `tailscale set --accept-dns=false`.
- Para algo **estável** (URL fixa), usar um **named tunnel** do Cloudflare (com
  conta) ou hospedar de fato (VM/PaaS + domínio). Decisão de negócio pendente.

## Lembretes (job)
Infra-agnóstico: dá pra disparar por
- **CLI**: `flask lembretes` (cron do sistema / GitHub Actions), ou
- **HTTP**: `POST /tarefas/lembretes` com `TAREFAS_TOKEN` (cron-job.org etc.).
Idempotente (`Agendamento.lembrete_enviado_em`).

## Versão & saúde
O boot loga `version` (commit) + `migration_head` + dialeto do DB. `/health`
expõe o mesmo (`services/app_info.py`) — útil pra confirmar o que está no ar.
