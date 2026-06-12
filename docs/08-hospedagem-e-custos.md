# 8. Hospedagem, Banco e Storage — Estudo de Opções e Custos

> **Para decisão de negócio (sócio).** Onde hospedar o Nous Clinical, com qual
> banco e storage, quanto custa cada caminho, e como migrar depois sem retrabalho.
> *Preços são faixas aproximadas (2025) — confirme no momento da contratação.
> Conversão usada: ~R$ 5,50/US$ e ~R$ 6,00/€.*

## O princípio que destrava a decisão: o sistema é PORTÁTIL
O Nous roda em **Docker**, usa **PostgreSQL** (padrão) e **storage S3-compatível**, e o **domínio é nosso** (`nousclinical.com`, na HostGator). Isso significa:
- A aplicação roda em **qualquer** servidor/PaaS que aceite Docker.
- O banco se move com `pg_dump`/restore (muda **1 variável**: `DATABASE_URL`).
- Os arquivos (logo/exames) se movem entre R2/S3/B2 **sem mexer no código**.
- O domínio só **reaponta** (DNS).

➡️ **A escolha de hoje NÃO é definitiva.** Dá pra começar no mais fácil e migrar pro mais barato quando crescer, sem reescrever nada.

## O sistema precisa de 3 peças (podem ser de fornecedores diferentes)
1. **Hospedagem da aplicação** — onde o código Python roda.
2. **Banco de dados** — PostgreSQL.
3. **Storage de arquivos** — logo da clínica + exames (dado sensível LGPD).
*(+ Domínio — já temos, fica na HostGator e só aponta.)*

---

## A) Hospedagem da aplicação
| Opção | Fornecedor | Custo/mês aprox. | Esforço seu | Observação |
|---|---|---|---|---|
| **PaaS gerenciado** ⭐ | **Render** | Free · US$7 (starter) · US$25 (standard) | **Baixo** (deploy do GitHub) | HTTPS automático, zero servidor. **É onde estamos.** Cobra em US$. |
| PaaS | Railway | ~US$5 + uso | Baixo | Simples, bom para começar. US$. |
| PaaS | Fly.io | ~US$5–10 | Médio | Rápido/edge, um pouco mais técnico. US$. |
| **VPS** | **Hetzner** (CX22) | ~€5 (~R$30) | **Alto** (SSH/Docker — nós montamos) | Muito barato e potente. Você administra. |
| VPS | DigitalOcean | US$6 (droplet) | Alto | Padrão de mercado. US$. |
| VPS | Contabo | ~€6 | Alto | Muito recurso por preço; I/O variável. |
| VPS | **HostGator BR** | ~R$120–250 | Alto | Tudo num fornecedor BR, suporte PT, cobra em R$. Caro pelas specs; confirmar VPS **com root** (não cPanel). |
| Compartilhado | HostGator cPanel | — | — | ❌ **Não roda Flask bem** (é PHP/MySQL). Não usar para a app. |

## B) Banco de dados (PostgreSQL)
| Fornecedor | Custo/mês aprox. | Observação |
|---|---|---|
| **Render Postgres** | Free (expira 90d) · US$6 (basic) | Fica junto da app no Render. |
| **Neon** | Free generoso · US$19 | Serverless (escala a zero). Ótimo e barato para começar. |
| Supabase | Free · US$25 (pro) | Postgres + extras. |
| No próprio VPS | **incluso** no VPS | Você administra + cuida do backup (`pg_dump`). |
| HostGator **MySQL** | incluso no plano | ❌ exigiria **migrar de Postgres p/ MySQL** (trabalho + risco de fuso). Não recomendado. |

## C) Storage de arquivos (logo + exames)
| Fornecedor | Custo/mês aprox. | Observação |
|---|---|---|
| **Cloudflare R2** ⭐ | **Free até 10GB** + US$0,015/GB; **sem taxa de saída** | Recomendado. S3-compatível. Sem custo de egress. |
| AWS S3 | US$0,023/GB + egress | Padrão, mas cobra saída de dados. |
| Backblaze B2 | US$0,006/GB | Mais barato em storage. |
| Disco no VPS | incluso | Só se a app estiver num VPS; você cuida do backup. |
| Render Persistent Disk | US$0,25/GB | Simples se já no Render (exige plano pago). |

> ⚠️ **Por que isso importa:** no plano grátis do Render o disco é efêmero — a logo e os **exames somem** quando a instância dorme/redeploya. Por isso o storage **tem** que ser externo (R2) em produção. Já deixamos o código pronto pra R2.

---

## Cenários recomendados (combos prontos, com custo total)

### Cenário 1 — Validação / MVP (o atual)
**Render Free + Render Postgres Free + R2 Free + domínio HostGator**
- **Custo: ~US$ 0** · Limites: app "dorme", banco expira em 90 dias.
- **Quando:** agora (homologação com o sócio). **Não** para dado real de paciente.

### Cenário 2 — Produção pequena, gerenciada ⭐ (recomendado para lançar)
**Render Starter (US$7) + Render Postgres Basic (US$6) + R2 (~US$0–1)**
- **Total: ~US$ 13–14/mês (~R$ 75)**
- Zero administração, HTTPS automático, deploy do GitHub. **Melhor custo × sossego** para começar de verdade.

### Cenário 3 — Produção econômica em VPS (mais barato; mais trabalho)
**Hetzner CX22 (~€5) rodando app + Postgres + Redis via Docker + R2 (~US$0–1)**
- **Total: ~€ 5–6/mês (~R$ 35)**
- Bem mais barato. Em troca, **você administra** (atualizações, backup, monitoramento) — nós montamos o servidor e deixamos automatizado.

### Cenário 4 — Tudo na HostGator (um fornecedor só, em BR)
**HostGator VPS (root) + Postgres no próprio VPS + R2 (ou disco) + domínio já lá**
- **Total: ~R$ 120–250/mês**
- **A favor:** tudo num lugar, suporte em português, cobrança em real.
- **Contra:** mais caro pelas specs, e exige o **mesmo** trabalho de SSH/Docker do Hetzner.

---

## Comparação rápida (resumo decisório)
| Eixo | Vence |
|---|---|
| Mais **fácil** (sem servidor) | **Render** (PaaS) |
| Mais **barato** | **Hetzner** (VPS) |
| **Tudo em BR** / suporte PT / real | **HostGator** (VPS) |
| **Melhor para lançar agora** | **Cenário 2** (Render pago + R2) |

## O que NÃO recomendamos
- **Hospedagem compartilhada (cPanel)** para a app — é ambiente PHP/MySQL, hostil a Python; e storage/banco compartilhado é ruim para dado médico (LGPD).
- **Migrar para MySQL** só para usar o banco incluso da HostGator — trabalho e risco sem ganho real.

## Recomendação final (nossa)
1. **Homologação (agora):** Cenário 1 — já está rodando, custo zero.
2. **Lançar de verdade:** **Cenário 2** (Render pago + R2) — ~R$ 75/mês, sem dor de cabeça, rápido de ativar.
3. **Quando o volume justificar economia:** migrar para o **Cenário 3** (Hetzner) — ~R$ 35/mês; nós fazemos a migração (app + dump do banco + bucket), sem reescrever o sistema.
4. **HostGator** faz sentido **só** se a prioridade do sócio for "um fornecedor brasileiro, suporte em português, tudo num lugar" e o orçamento aceitar o custo maior.

> **Mensagem-chave para o sócio:** não estamos presos a ninguém. Começamos barato e fácil (Render + R2), e trocamos de fornecedor quando fizer sentido — é cópia de dados + reapontar o domínio, não recomeçar o projeto.
