# 13 — Chatbot de ajuda "Suporte Nous": como foi construído

> Doc **técnico** (para devs): o que usamos, as decisões que tomamos e como o
> chatbot funciona por dentro. A visão de usuário está no
> [Manual, cap. 13](manual/13-assistente-ia.md); as regras de escrita da base de
> conhecimento estão em [docs/ajuda/README.md](ajuda/README.md).

## O que é (em uma frase)

Um widget de chat embutido em todas as telas logadas que responde dúvidas de
**uso do sistema** ("como agendar?", "onde recebo pagamento?") buscando numa
base de conhecimento em Markdown versionada no próprio repositório — com um
modo IA opcional (Claude Haiku) por cima, desligado por padrão.

## Arquitetura em duas camadas (decisão central)

```
┌─ Browser ──────────────────────────────────────────────┐
│ ajuda-widget.js (vanilla, CSP-safe, ~110 linhas)       │
│   balão flutuante + chips de FAQ + histórico da sessão │
└───────────────┬────────────────────────────────────────┘
                │ POST same-origin (CSRF + cookie de sessão)
┌─ Flask ───────▼────────────────────────────────────────┐
│ /ajuda/buscar  → buscar_local()   CAMADA 1: custo zero │
│ /ajuda/chat    → responder()      CAMADA 2: IA opt-in  │
│        (app/routes/ajuda.py + app/services/ajuda.py)   │
└───────────────┬───────────────────────────┬────────────┘
                │ lê e filtra por papel     │ só se AJUDA_IA_ATIVA
┌───────────────▼──────────────┐   ┌────────▼───────────────┐
│ docs/ajuda/*.md (13 docs)    │   │ API Anthropic          │
│ frontmatter: modulo + papeis │   │ Claude Haiku, cacheado │
└──────────────────────────────┘   └────────────────────────┘
```

- **Camada 1 — Suporte local (o que roda em produção, sempre ON):** busca
  lexical própria, sem nenhuma chamada externa, sem custo, sem chave. É o que o
  widget usa por padrão.
- **Camada 2 — Assistente IA (default-OFF):** mesma base de conhecimento, mas a
  resposta é redigida pelo Claude Haiku. Liga com 2 variáveis de ambiente
  (`AJUDA_IA_ATIVA=true` + `ANTHROPIC_API_KEY`); se a IA falhar, o produto não
  quebra — o widget continua com a camada 1.

**Por que não RAG/embeddings/vector store?** A base é pequena (13 documentos
curados) e o domínio é fechado (uso do sistema). Uma busca lexical com boas
heurísticas resolve com custo zero e zero infra. Complexidade de RAG só se
justificaria com base grande/heterogênea — não é o caso, e a decisão mantém o
chatbot grátis para todas as clínicas.

## O que usamos (stack)

| Peça | Escolha | Observação |
|---|---|---|
| Backend | Flask (blueprint `ajuda_bp`) | mesmo app, sem serviço separado |
| Busca | Python puro (`unicodedata` + `re`) | sem lib de NLP, sem índice externo |
| Base de conhecimento | Markdown versionado (`docs/ajuda/`) | PR = atualizar o bot |
| IA (opcional) | SDK `anthropic`, modelo `claude-haiku-4-5` | import lazy; roda sem a lib instalada |
| Frontend | JS vanilla CSP-safe + tokens CSS do design system | sem framework, sem inline handler |
| Rate-limit | Flask-Limiter, chave **por usuário** | clínica inteira sai pelo mesmo IP público |
| Testes | pytest com a API mockada | nenhum teste toca a rede |

## Como desenvolvemos (linha do tempo real dos commits)

1. **`7426a33` — Fase A:** chatbot "Nous Assistente" com IA + a base de
   conhecimento inicial em `docs/ajuda/` (a base nasceu junto com o bot — o
   conteúdo é o produto, o código é o entregador).
2. **`76d2664` — auditoria multi-agente:** o módulo passou por revisão de
   segurança com múltiplos agentes; polimos os achados P1/P2 (anti-injeção,
   fail-closed do filtro de papéis, auditoria sem PII).
3. **`3936f33` — inversão da estratégia:** percebemos que a maioria das dúvidas
   se resolvia com a própria base → criamos o **modo local de custo zero** e o
   promovemos a padrão ("Suporte Nous"), rebaixando a IA a opt-in. Widget
   redesenhado nessa leva.

## Camada 1 em detalhe — a busca local (`buscar_local`)

1. **Indexação (lazy + cache em módulo):** cada `.md` é quebrado em seções por
   heading (`#`–`####`); no FAQ, cada pergunta em `**negrito**` também vira
   seção. Cache por papel, invalidado só no restart (a base muda via deploy).
2. **Normalização:** minúsculas + remoção de acento (`NFKD`) + só
   alfanumérico → "Convênio" bate com "convenio".
3. **Tokenização:** termos com ≥3 caracteres, filtrados por uma lista de
   stopwords PT-BR própria ("como", "faço", "quero"…).
4. **Ranking:** termo no **título vale 5 pontos**; no corpo, 1 ponto por
   ocorrência. Score mínimo 2 — abaixo disso o bot **admite que não sabe** em
   vez de chutar (honestidade > cobertura).
5. **Resposta:** a melhor seção, com o Markdown limpo (links viram texto,
   imagens caem), truncada em ~700 caracteres, com a **fonte** (título da
   seção) exibida como tag no balão.
6. **Chips de sugestão:** as 6 primeiras perguntas do `faq.md` visíveis ao
   papel do usuário viram botões de primeiro clique.

## Camada 2 em detalhe — o modo IA (`responder`)

- **System prompt em 2 blocos:** (1) a persona com 7 regras invioláveis (só
  uso do sistema; **nunca** orientação clínica; nunca inventar dado; respeitar
  o papel; admitir o que não existe) e (2) a base de conhecimento filtrada por
  papel com **`cache_control: ephemeral`** → prompt caching da Anthropic corta
  o custo das perguntas seguintes.
- **Anti-injeção:** a pergunta viaja delimitada em `<pergunta>…</pergunta>` e a
  persona instrui a tratar tudo ali como dado, não comando.
- **Memória:** histórico curto (últimas 6 mensagens) vive **no browser** e é
  reenviado a cada chamada — o servidor não guarda conversa nenhuma.
- **Falha nunca derruba:** `responder()` é best-effort; erros são mapeados por
  classe (rate-limit → "aguarde"; chave revogada → "avise o administrador") e
  o request sempre retorna 200 com uma mensagem digna.

## Segurança, LGPD e custo (o que nos deixou confortáveis em ligar)

- **Chave só no servidor** — o browser nunca vê a `ANTHROPIC_API_KEY`.
- **Gates:** `login_required` + `equipe_required` + CSRF em ambas as rotas.
- **Rate-limit por usuário** (não por IP): 120/h na busca local; **20/h e
  4/min** na IA — o teto de custo por usuário é conhecido.
- **Filtro por papel fail-closed:** doc com frontmatter `papeis:` malformado
  fica visível para **ninguém** (nunca vaza doc sensível por erro de sintaxe).
- **Zero PII:** o bot não acessa banco de dados; a auditoria grava só metadado
  (`papel` + tamanho da pergunta), **nunca o texto** — para não criar um novo
  repositório de dado pessoal.
- **CSP estrita mantida:** widget sem inline handler/estilo; `textContent` em
  tudo que vem do servidor (sem XSS por resposta).

## Arquivos do módulo

| Arquivo | Papel |
|---|---|
| `app/services/ajuda.py` | busca local + modo IA + persona (~290 linhas) |
| `app/routes/ajuda.py` | rotas `/ajuda/buscar` e `/ajuda/chat` (gates + limites) |
| `app/static/js/ajuda-widget.js` | widget do balão (vanilla, CSP-safe) |
| `app/templates/base.html` | markup do widget (presente em toda tela logada) |
| `docs/ajuda/*.md` | base de conhecimento (13 docs com frontmatter) |
| `tests/test_ajuda.py` + `tests/test_ajuda_suporte.py` | suíte (API mockada) |

## Como ligar o modo IA (quando quisermos)

```
AJUDA_IA_ATIVA=true
ANTHROPIC_API_KEY=sk-ant-...        # só no painel do provedor, nunca no git
MODEL_AJUDA=claude-haiku-4-5        # default; ~US$1/1M tokens de entrada
```

Sem essas variáveis o widget segue funcionando na camada 1 — foi desenhado
para que o "desligado" seja indistinguível de produto completo.
