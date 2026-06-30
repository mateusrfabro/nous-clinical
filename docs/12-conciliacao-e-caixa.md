# 12. Conciliação bancária & fechamento de caixa

> Dois módulos do financeiro que fecham o ciclo do dinheiro: **conciliação**
> (casar o extrato do banco com os lançamentos do sistema) e **fechamento de
> caixa** (conferir o esperado do dia contra o contado na recepção). Ambos sob o
> gate `recepcao_ou_admin` (profissional não vê), em `app/routes/financeiro.py`.

## TL;DR
- **Conciliação:** o usuário importa o extrato (OFX ou CSV) → cada linha vira um
  `MovimentoBancario` (dedup por `fitid`) → o sistema sugere o `LancamentoFinanceiro`
  correspondente (mesmo valor + tipo + data próxima) → o usuário confirma, cria um
  lançamento novo, ou ignora. Vínculo **1:1** movimento↔lançamento.
- **Caixa:** o esperado é **sempre recalculado no servidor** (receitas pagas no dia,
  por forma de pagamento); o usuário digita o contado; grava-se a divergência. **Um
  fechamento por (clínica, dia)** — reabrir apaga o registro.

---

## 1. Modelos (`app/models.py`)

### `MovimentoBancario` — transação do extrato
Uma linha do extrato bancário importada para conciliar. Campos:
- `data` (**`Date`** — sem hora/fuso; o `DTPOSTED` do OFX é uma data), `valor`
  (**`Numeric(12,2)`**, **sempre positivo** — o sentido vai em `tipo`), `tipo`
  (`credito`=entrada / `debito`=saída), `descricao` (MEMO/NAME), `conta` (ACCTID),
  `banco` (ORG/BANKID, exibição), `fitid` (id único da transação no banco).
- `status` ∈ `{pendente, conciliado, ignorado}` (default `pendente`).
- `lancamento_id` → `LancamentoFinanceiro` (**`unique`** → relação **1:1**;
  `back_populates="movimento"`). `conciliado_em`/`conciliado_por_id`,
  `importado_em`/`importado_por_id` (trilha).
- **Dedup de reimportação:** `UniqueConstraint(clinica_id, conta, fitid)`
  (`uq_mov_fitid`). Reimportar o mesmo extrato não duplica linhas — `importar_extrato`
  pula os `fitid` já presentes na conta. Índice composto
  `ix_mov_clinica_status_data(clinica_id, status, data)` para o painel.

### `FechamentoCaixa` — fechamento diário
Confere o **esperado** (receitas pagas no dia, por forma de pagamento) contra o
**contado** pela recepção. Campos:
- `dia` (**`Date`**, fuso BR resolvido na rota), `esperado_total`, `contado_total`,
  `divergencia` (**`Numeric(12,2)`** — `contado − esperado`), `observacoes`.
- `detalhes` (**`Text` com JSON**): `{forma: {esperado, contado}}` — snapshot por
  forma de pagamento no momento do fechamento. `fechado_por_id`/`fechado_em`.
- **Um por (clínica, dia):** `UniqueConstraint(clinica_id, dia)` (`uq_fechamento_dia`).
  **Reabrir = deletar** o registro (não há flag "reaberto"); refechar recria.

> Ambos carregam `clinica_id` e estão registrados em `escopados` no
> `app/services/tenant.py` — o escopo automático por clínica se aplica nas queries.

---

## 2. Parser de extrato

### OFX (`app/services/ofx.py`)
`parse_ofx(bytes|str) -> ExtratoOFX` tolera os dois sabores que os bancos BR
exportam, **sem dependência externa** (regex sobre o texto, não um parser SGML/XML
completo):
- **OFX 1.x (SGML):** tags-folha sem fechamento (`<TRNAMT>150.00` termina na quebra
  de linha), agregados com fechamento (`<STMTTRN>...</STMTTRN>`).
- **OFX 2.x (XML):** tags com fechamento (`<TRNAMT>150.00</TRNAMT>`).

A função `_campo(bloco, tag)` captura o valor de uma tag **do `>` até a quebra de
linha OU o próximo `<`** — funciona nos dois formatos. Detalhes:
- `_decodifica` tenta `utf-8 → cp1252 → latin-1` (1.x costuma ser cp1252).
- Cada `STMTTRN` vira um `TransacaoOFX(data, valor, tipo, descricao, fitid)`:
  `valor = abs(TRNAMT)` quantizado a 2 casas; `tipo = "credito" if TRNAMT >= 0 else "debito"`;
  `descricao = MEMO or NAME` (≤200); `data` dos 8 primeiros dígitos do `DTPOSTED`.
- Lança **`OFXError`** se o arquivo não parece OFX ou não tem nenhum `STMTTRN`.

### Dispatcher + CSV (`app/services/extrato.py`)
`parse_extrato(filename, conteudo)` despacha pelo nome: `.csv` → `parse_csv`;
qualquer outro → `parse_ofx`. O CSV varia muito por banco, então `parse_csv` é
**tolerante**:
- **Delimitador** detectado por contagem: `;` se houver `≥` `,`, senão `,`.
- **Cabeçalho** achado pelas palavras-chave das colunas — `data`/`date`,
  `valor`/`amount`/`montante`, `histor`/`descri`/`memo`/`lancamento`…, e
  crédito/débito em colunas separadas. Ignora preâmbulo antes do cabeçalho.
- **Número BR** (`_num_br`): se há vírgula, ela é o decimal e o ponto é milhar
  (`1.234,56 → 1234.56`); tolera `R$`/sinal. **Data** (`_data_br`): `dd/mm/aaaa`
  ou `aaaa-mm-dd`.
- Banco com débito/crédito em colunas separadas: `valor = credito − debito`.
- **`fitid` sintetizado:** CSV raramente traz id de transação, então gera
  `"csv" + sha1("data|valor|descrição")[:16]` — habilita o **mesmo dedup de
  reimportação** do OFX. Lança `OFXError` se não achar colunas ou nenhuma linha.

Ambos os parsers devolvem o mesmo `ExtratoOFX(banco, conta, transacoes)` —
o resto do fluxo não distingue a origem.

---

## 3. Serviço de conciliação (`app/services/conciliacao.py`)

- **`importar_extrato(extrato, clinica_id, usuario_id) -> (novos, duplicados)`** —
  cria os `MovimentoBancario`. Carrega os `fitid` já importados da conta e **pula
  os duplicados** (o escopo de clínica é automático na query). Commita.
- **`sugestao_para(mov) -> LancamentoFinanceiro | None`** — a **sugestão automática**
  (não altera nada). Casa por: tipo compatível (crédito↔receita, débito↔despesa),
  **valor exato igual**, lançamento **não cancelado** e **ainda não conciliado**
  (sem movimento apontando pra ele), e **data dentro de ±7 dias** (`_JANELA_DIAS`).
  A data de referência do lançamento é `pago_em → vencimento → criado_em`
  (`_data_lancamento`, em fuso BR). Entre vários candidatos, vence o de data mais
  próxima.
- **`candidatos_para(mov, limite=50)`** — para a **conciliação manual** (quando o
  valor não bate com a sugestão). Mesma regra de tipo/não-conciliado, **sem corte
  de janela**: lista tudo, ordenado por proximidade de data e desempatando por
  `|diferença de valor|`.
- **`lancamentos_nao_conciliados(clinica_id, desde)`** — o **outro lado da
  divergência**: receitas **pagas** desde uma data que ainda **não** têm movimento
  conciliado (esperado no banco, mas não apareceu no extrato).

---

## 4. Rotas (`app/routes/financeiro.py`)

### Conciliação
| Rota | Método | O que faz |
|---|---|---|
| `/financeiro/conciliacao` | GET | Painel: movimentos (pendentes primeiro) + sugestão por pendente + contadores (`n_pend`, `n_conc`, `n_sem_extrato`). |
| `/financeiro/conciliacao/importar` | POST | Recebe o arquivo (`extrato`), `parse_extrato` + `importar_extrato`. Audita `ACAO_CONCILIACAO_IMPORT`. |
| `/financeiro/conciliacao/<id>` | GET | Detalhe = **conciliação manual**: lista `candidatos_para(mov)` pra escolher. |
| `/financeiro/conciliacao/<id>/conciliar` | POST | Casa o movimento a um `lancamento_id` existente (vindo da sugestão). Recusa se o lançamento já tem outro movimento. |
| `/financeiro/conciliacao/<id>/criar` | POST | **Cria** um `LancamentoFinanceiro` pago a partir do movimento (data do extrato ao meio-dia BR) e já concilia. Audita criação + conciliação. |
| `/financeiro/conciliacao/<id>/ignorar` | POST | Marca como `ignorado` (tarifa, transferência interna…). Só se não conciliado. |
| `/financeiro/conciliacao/<id>/desfazer` | POST | Volta pra `pendente`, **desfaz só o vínculo** — não apaga o lançamento. |
| `/financeiro/conciliacao/divergencias` | GET | Os dois lados num período (`?dias`, 1–365): movimentos pendentes × receitas pagas sem extrato, com totais. |

### Fechamento de caixa
| Rota | Método | O que faz |
|---|---|---|
| `/financeiro/caixa` | GET | Caixa do dia (`?dia`): esperado por forma (`_esperado_por_forma`) × contado. Mostra o fechamento existente, se houver. |
| `/financeiro/caixa/fechar` | POST | Recalcula o esperado **no servidor** (não confia no cliente), lê o contado por forma, grava `esperado/contado/divergencia` + `detalhes` JSON. Upsert por dia. Audita `ACAO_CAIXA_FECHADO`. |
| `/financeiro/caixa/<id>/reabrir` | POST | **Deleta** o fechamento (não há "reaberto"). Audita `ACAO_CAIXA_REABERTO`. |

Helper `_esperado_por_forma(dia)`: soma as receitas **pagas** no dia (janela de
meia-noite a meia-noite **fuso BR → UTC**, casando com `pago_em`) agrupadas por
`forma_pagamento` (NULL → `nao_informada`).

### Defesa em profundidade: `_get_tenant`
`_get_tenant(Model, id_)` (no topo do blueprint) faz `db.session.get` **e** recusa
explicitamente objeto de outra clínica (`obj.clinica_id != current_user.clinica_id`
→ `None`), além do escopo automático do tenant loader — blinda contra qualquer
caminho que furasse o escopo. As rotas de movimento usam `_mov_ou_redirect`, que o
embrulha com um flash + redirect.

---

## 5. Fluxo da conciliação (diagrama textual)

```
Extrato do banco (.ofx | .csv)
        │  POST /conciliacao/importar
        ▼
parse_extrato ── .csv → parse_csv (delim, núm/data BR, fitid=sha1)
        │       └ outro → parse_ofx (SGML 1.x | XML 2.x)
        ▼
ExtratoOFX(banco, conta, transacoes[])
        │  importar_extrato — dedup por (clinica, conta, fitid)
        ▼
MovimentoBancario (status=pendente)  ──────────────┐
        │                                          │
        │  painel /conciliacao                     │ sugestao_para(mov)
        ▼                                          ▼   (valor+tipo+data ±7d)
  ┌──────────────┬──────────────┬─────────────┐  LancamentoFinanceiro sugerido
  │  conciliar   │    criar     │   ignorar   │
  │ (casa um     │ (cria lanç.  │ (tarifa,    │
  │  existente)  │  pago + casa)│  transfer.) │
  ▼              ▼              ▼
status=conciliado            status=ignorado
(lancamento_id 1:1)                 │
        │                           │  desfazer
        └───────────┬───────────────┘  (→ pendente, desfaz vínculo)
                    ▼
   /conciliacao/divergencias:
   movimentos pendentes  ×  receitas pagas sem extrato
   (lancamentos_nao_conciliados)
```
