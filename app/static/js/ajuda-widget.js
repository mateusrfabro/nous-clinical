/* ajuda-widget.js — Suporte Nous (ajuda de uso do sistema).
 *
 * Custo zero: fala com /ajuda/buscar (same-origin, CSRF), que responde buscando
 * na base de ajuda local — sem nenhuma chamada de IA/API. CSP-safe: sem inline
 * handler/estilo; mostra/oculta via classe e atributo hidden. No-op fora da página.
 */
(function () {
  "use strict";

  var wrap = document.querySelector(".ajuda-wrap");
  if (!wrap) return;
  var fab = document.getElementById("ajuda-toggle");
  var painel = document.getElementById("ajuda-panel");
  var fechar = document.getElementById("ajuda-close");
  var form = document.getElementById("ajuda-form");
  var input = document.getElementById("ajuda-input");
  var msgs = document.getElementById("ajuda-msgs");
  var enviar = document.getElementById("ajuda-send");
  var chips = document.getElementById("ajuda-chips");
  if (!painel || !form || !input || !msgs) return;

  var csrf = painel.getAttribute("data-csrf") || "";
  var ocupado = false;

  function abrir(mostrar) {
    painel.hidden = !mostrar;
    wrap.classList.toggle("is-open", mostrar);
    fab.setAttribute("aria-expanded", String(mostrar));
    if (mostrar) input.focus();
  }

  function bolha(texto, classe, fonte) {
    var div = document.createElement("div");
    div.className = "ajuda-msg " + classe;
    if (fonte) {
      var tag = document.createElement("span");
      tag.className = "ajuda-fonte";
      tag.textContent = fonte;
      div.appendChild(tag);
    }
    var p = document.createElement("span");
    p.className = "ajuda-texto";
    p.textContent = texto;
    div.appendChild(p);
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return div;
  }

  function digitando() {
    var div = document.createElement("div");
    div.className = "ajuda-msg ajuda-bot ajuda-typing";
    div.innerHTML = '<span class="ajuda-dot"></span><span class="ajuda-dot"></span><span class="ajuda-dot"></span>';
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return div;
  }

  function perguntar(texto) {
    var pergunta = (texto || "").trim();
    if (!pergunta || ocupado) return;
    if (chips) chips.remove();
    bolha(pergunta, "ajuda-user");
    input.value = "";
    ocupado = true;
    if (enviar) enviar.disabled = true;
    var carregando = digitando();

    fetch("/ajuda/buscar", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify({ pergunta: pergunta })
    })
      .then(function (r) { return r.ok ? r.json() : { ok: false, resposta: "Erro de conexão." }; })
      .then(function (d) {
        carregando.remove();
        bolha((d && d.resposta) || "Não consegui responder.", "ajuda-bot",
              d && d.ok ? (d.fonte || null) : null);
      })
      .catch(function () {
        carregando.remove();
        bolha("Falha ao buscar a ajuda. Tente de novo.", "ajuda-bot");
      })
      .then(function () {
        ocupado = false;
        if (enviar) enviar.disabled = false;
        input.focus();
      });
  }

  fab.addEventListener("click", function () { abrir(painel.hidden); });
  if (fechar) fechar.addEventListener("click", function () { abrir(false); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !painel.hidden) abrir(false);
  });

  if (chips) {
    chips.addEventListener("click", function (e) {
      var b = e.target.closest(".ajuda-chip");
      if (b) perguntar(b.getAttribute("data-q"));
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    perguntar(input.value);
  });
})();
