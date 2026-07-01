# 11. Emissão de Nota Fiscal (NFS-e) — decisão e arquitetura

> **Status:** desenho aprovado para implementação faseada (pesquisa concluída em
> 23/06/2026). **Documento interno (dev/projeto).** Os pré-requisitos do cliente
> (seção 3) viram material de onboarding quando o módulo for lançado.

Clínica emite **NFS-e** (nota fiscal de **serviço**, imposto **ISS**, **municipal**).
Cada clínica é um **emitente** (CNPJ) próprio, possivelmente em cidade diferente — logo
o módulo é **multi-tenant e opcional por clínica** (igual ao WhatsApp): só a clínica que
tiver os pré-requisitos fiscais habilita e vê o módulo.

## 1. Decisão de provedor

NFS-e é **municipal** (~5.500 prefeituras). Não integramos cidade a cidade — usamos um
**gateway/agregador** que abstrai os municípios, cuida do certificado, do status
assíncrono e do PDF/XML. A **NFS-e Nacional** (API oficial `gov.br/nfse`, padrão único)
está virando obrigatória a partir de **jan/2026 (LC 214/2025)**, com rollout cidade a
cidade — no futuro pode permitir integração direta sem gateway.

**Decisão:**
- **Começar pela Nuvem Fiscal** — CNPJs emitentes **ilimitados em qualquer plano
  (inclusive o grátis)**, REST moderno, docs primárias boas, cota por documento emitido.
  Ideal para multi-tenant ainda sem cliente (custo inicial ~zero).
- **Focus NFe como plano B/cobertura** — 3.000+ municípios e **garante integrar cidade
  nova** (R$199 / 15 dias úteis). PlugNotas/eNotas como alternativas.
- **Construir atrás de um ADAPTADOR** (interface única): nenhum gateway cobre 100% das
  cidades; o adaptador permite **rotear por cidade** e **trocar/somar provedor** sem
  reescrever o módulo. Também deixa a porta aberta pra ir direto na NFS-e Nacional depois.

| Gateway | Cobertura | Multi-CNPJ | Preço (mês) | Certificado |
|---|---|---|---|---|
| **Nuvem Fiscal** ⭐ | 1.845 cidades + endpoint p/ checar | **ilimitado, até no grátis** | grátis + cota por documento | A1 (Base64, no provedor) |
| **Focus NFe** | 3.000+ (integra cidade nova R$199/15d) | vários por conta | Solo R$89,90 · Growth R$548 (ilimitado) | só A1 |
| **PlugNotas** | 1.600+ | sim | (confirmar) | só A1 |
| **eNotas** | 500+ | sim | R$137 / R$247 / R$347 | A1 eCNPJ |

> Confiança: cobertura da Focus e preços/cobertura da eNotas tiveram verificação parcial
> (2-1); números de "% de cobertura nacional" **não** foram confirmados. **Antes de
> fechar contrato, confirmar preço + cobertura da cidade específica direto no provedor.**

## 2. Arquitetura no Nous

### 2.1 Modelos (`app/models.py`)
- **`ConfigFiscalClinica`** — 1:1 com `Clinica`. `ativo` (flag por tenant), `gateway`
  (`nuvemfiscal`/`focusnfe`/…), `gateway_empresa_id` (id do emitente no gateway),
  `api_token_cifrado` (segredo do gateway, **cifrado** via `services/cripto.py`),
  `certificado_validade` (o A1 vai pro gateway; guardamos só status/validade),
  `inscricao_municipal`, `regime_tributario`, `aliquota_iss` (`Numeric`), `codigo_servico`
  (LC116), `cnae`, `cnpj`, `razao_social`, `codigo_municipio_ibge`, `iss_retido_padrao`.
- **`NotaFiscal`** — `clinica_id`, `lancamento_id` (1:1 opcional com `LancamentoFinanceiro`),
  `paciente_id`, `atendimento_id` (opcional), `status`
  (`rascunho|enviando|autorizada|rejeitada|cancelada|erro`), `gateway`, `gateway_nota_id`,
  `numero`, `codigo_verificacao`, `chave_acesso`, `valor` (**`Numeric(12,2)`**),
  `descricao_servico`, `codigo_servico`, `aliquota_iss`, `iss_valor`, `data_emissao`,
  `link_pdf`, `link_xml`, `mensagem_erro`, timestamps.
- Auditoria: `ACAO_FISCAL_CONFIG`, `ACAO_NF_EMITIDA`, `ACAO_NF_CANCELADA`.

### 2.2 Adaptador de gateway (`app/services/fiscal/`)
- `base.py` — interface `GatewayNFSe`: `cadastrar_emitente(config)`,
  `emitir(dados) -> resultado`, `consultar(id)`, `cancelar(id, motivo)`, `pdf/xml(id)`.
- `nuvemfiscal.py`, `focusnfe.py` — implementações (HTTP **server-side**; segredos vêm da
  `ConfigFiscalClinica` decifrada).
- `__init__.py` — fábrica `get_gateway(clinica)` que escolhe pelo config (e, no futuro,
  roteia por município).

### 2.3 Fluxo de emissão
```
1. Admin habilita o módulo: /configuracoes/fiscal (admin_required)
   -> preenche IM, regime, ISS, código serviço; envia o certificado A1
   -> backend cadastra o emitente no gateway, guarda gateway_empresa_id, valida
2. No recebimento pago (LancamentoFinanceiro), botão "Emitir NF" (só se ativo)
   -> monta dados: tomador = paciente (CPF/nome); serviço = descrição GENÉRICA
      ("Serviços de saúde", conforme a profissão); valor; código LC116; ISS
   -> gateway.emitir() -> cria NotaFiscal status=enviando
3. Status assíncrono: webhook do gateway -> /fiscal/webhook (fail-closed, assinado)
   -> autorizada (numero, pdf, xml) | rejeitada (mensagem_erro)
4. Tela de notas: listar, baixar PDF/XML, cancelar (motivo) -> gateway.cancelar()
```

### 2.3.1 Mapa da API Nuvem Fiscal (Fase 2 — confirmado na referência)
- **Cadastrar emitente:** `POST /empresas` — `cpf_cnpj`, `nome_razao_social`, `email`,
  `inscricao_municipal`, `endereco{logradouro, numero, bairro, codigo_municipio, cidade,
  uf, cep}`. **Não exige certificado.**
- **Certificado A1:** `PUT /empresas/{cpf_cnpj}/certificado` — `{certificado: <base64 do
  .pfx>, password}`. **Exigido para emitir.**
- **Configurar NFS-e:** `PUT /empresas/{cpf_cnpj}/nfse` — `regTrib{opSimpNac,...}`,
  `ambiente` (`homologacao|producao`), série/numeração RPS.
- **Emitir:** `POST /nfse` — `declaracao_prestacao_servico{ rps, competencia, prestador,
  tomador, servicos[{ item_lista_servico (LC116), codigo_municipio, codigo_tributacao_
  municipio, discriminacao (genérica!), aliquota_iss, valores{valor_servicos, valor_iss,
  valor_liquido,...} }] }`. Consulta/cancelamento por eventos.
- **Implicação de sequência:** cadastrar empresa → subir certificado A1 → configurar NFS-e
  → emitir. **A partir do certificado, tudo precisa de um A1 válido** (mesmo no sandbox).

### 2.4 Gating por tenant (igual WhatsApp)
- Flag global **`NF_ATIVO`** (default **off**) + `ConfigFiscalClinica.ativo` por clínica.
  Menu/botões só aparecem com ambos ligados. **Inerte e sem custo até configurar.**

### 2.5 Segurança / LGPD
- Segredos do gateway **cifrados** (`services/cripto.py`, Fernet — já usado no WhatsApp).
- O **certificado A1 vai pro gateway**, não fica no nosso servidor → menos exposição.
- Escopo por `clinica_id` (anti-IDOR); webhook **fail-closed** + assinatura.
- **Descrição da nota genérica** (sigilo profissional + LGPD) — nunca diagnóstico/procedimento.
- A nota guarda **CPF do paciente** (PII) → tratar como dado pessoal; acesso auditado.
- Dinheiro sempre **`Numeric(12,2)`**.

## 3. Pré-requisitos do CLIENTE (clínica) — onboarding
1. **Certificado digital A1 e-CNPJ** (`.pfx` + senha). **A3 (token/cartão) não serve** —
   emissão é automática.
2. **Inscrição Municipal** ativa, habilitada a emitir NFS-e na prefeitura.
3. **Regime tributário** (Simples Nacional × Lucro Presumido/Real).
4. **Alíquota de ISS** do município (e se há ISS retido).
5. **Código de serviço LC 116** — **varia por profissão** (ex.: medicina **4.01** consultas /
   odontologia **4.02** / clínicas e hospitais **4.03**), com o CNAE correspondente.
6. Dados cadastrais do prestador (razão social, CNPJ, endereço).

## 4. Específico de serviços de saúde
- Descrição genérica ("Serviços de saúde"/"Consulta", conforme a profissão) — sigilo + LGPD.
- **CPF do paciente** como tomador (PF). Sem retenções no geral quando o tomador é PF;
  retenções (ISS/IRRF/PIS/COFINS/CSLL) só quando o tomador é PJ (convênio/empresa).

## 5. Plano de implementação (faseado)
- **Fase 0 (feito):** pesquisa + este desenho.
- **Fase 1:** `ConfigFiscalClinica` + tela `/configuracoes/fiscal` + cadastro do emitente
  no gateway (sandbox Nuvem Fiscal). Migration + testes.
- **Fase 2:** `NotaFiscal` + botão "Emitir NF" no recebimento + status via webhook +
  listar/baixar PDF (happy path, sandbox).
- **Fase 3:** cancelamento, rejeições/erros, substituição.
- **Fase 4:** segundo gateway (Focus) + roteamento por cidade no adaptador.
- **Fase 5:** automação opcional (emitir ao receber) + relatórios fiscais.

## 6. Fontes (verificadas)
gov.br/nfse (API nacional + manual técnico out/2025) · dev.nuvemfiscal.com.br/docs ·
focusnfe.com.br/precos · enotass.com.br · plugnotas.com.br/nfse · WebmaniaBR (CNAE×LC116)
