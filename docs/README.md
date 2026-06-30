# Documentação de desenvolvimento — Nous Clinical

Guia técnico para **quem desenvolve** o Nous Clinical (SaaS de gestão de clínica
multi-tenant em Flask). Objetivo: um dev novo entrar e ser produtivo sem
depender de ninguém.

> Para o "guia rápido do agente/dev" (papéis, padrões invioláveis, ambiente),
> veja também o [`CLAUDE.md`](../CLAUDE.md) na raiz — é o resumo executivo; aqui
> está o detalhe.

## Índice

1. [Arquitetura & visão geral](01-arquitetura.md) — stack, blueprints, services, ciclo de request.
2. [Setup & run](02-setup-e-run.md) — rodar local, migrations, seed, testes, variáveis de ambiente.
3. [Modelo de domínio](03-modelo-de-dominio.md) — entidades, relações e regras de negócio.
4. [Multi-tenant & RBAC](04-multitenant-e-rbac.md) — o escopo automático por clínica e os papéis. **Leia antes de mexer em qualquer rota.**
5. [White-label](05-white-label.md) — temas/cor/logo, portal por slug (`/c/<slug>`), favicon, QR.
6. [Deploy](06-deploy.md) — Docker/Compose, Cloudflare, checklist de produção.
7. [Convenções & como adicionar uma feature](07-convencoes.md) — padrões invioláveis e o passo a passo.
8. [Hospedagem & custos](08-hospedagem-e-custos.md) — provedores, planos e estimativa de custo.
9. [Checklist de produção](09-checklist-producao.md) — o que conferir antes de subir.
10. [Integração WhatsApp](10-whatsapp-integracao.md) — Cloud API, webhook, envio e **lembrete por template (HSM)**.
11. [Emissão de NFS-e](11-emissao-nf.md) — gateway, certificado, status do módulo fiscal.
12. [Conciliação bancária & fechamento de caixa](12-conciliacao-e-caixa.md) — modelos, parsers OFX/CSV, match e rotas.

> **Documentos não-técnicos:** [`PRODUCAO-STATUS-PENDENCIAS.md`](PRODUCAO-STATUS-PENDENCIAS.md)
> (status/pendências interno), [`COMERCIAL-NOUS.md`](COMERCIAL-NOUS.md) (apresentação
> comercial), `manual/` (manual do usuário final) e `ajuda/` (base do Suporte Nous).

## Mapa rápido do repositório

```
app/
  __init__.py        # app factory: extensões, CSP, blueprints, filtros/context Jinja
  models.py          # todas as entidades (SQLAlchemy)
  auth_decorators.py # decorators de papel (RBAC)
  permissions.py     # matriz de permissões legível + global Jinja pode()
  routes/            # um blueprint por arquivo (17)
  services/          # lógica sem HTTP: tenant, audit, storage, cores, lembretes...
  templates/         # Jinja2 (base.html é o shell)
  static/            # css/ (1 arquivo), js/ (CSP-safe), favicon.svg
migrations/versions/ # Alembic
tests/               # pytest (a suíte é a rede de segurança — rode sempre)
scripts/             # seed.py, seed_demo_clinicas.py
config.py            # Config por ambiente (development/testing/production)
run.py               # entrypoint dev (gunicorn em prod)
```

## A regra de ouro

Toda mudança passa por: **migration (se mexe em modelo) → rota (pensar
IDOR/CSRF/papel) → template (CSP, sem `style=` inline) → teste → commit
granular**. Detalhe em [07-convencoes.md](07-convencoes.md).
