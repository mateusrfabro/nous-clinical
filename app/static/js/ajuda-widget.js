/* ajuda-widget.js — Nous Assistente (chatbot de ajuda de uso do sistema).
 *
 * CSP-safe: sem inline handler/estilo; mostra/oculta via classe e atributo
 * hidden. Fala com /ajuda/chat (same-origin) com CSRF; o histórico curto vive
 * só na memória do browser. No-op se o widget não estiver na página.
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
  if (!painel || !form || !input || !msgs) return;

  var csrf = painel.getAttribute("data-csrf") || "";
  var historico = [];       // {role, content} — só nesta sessão de browser
  var ocupado = false;

  function abrir(mostrar) {
    painel.hidden = !mostrar;
    wrap.classList.toggle("is-open", mostrar);
    fab.setAttribute("aria-expanded", String(mostrar));
    if (mostrar) input.focus();
  }

  function bolha(texto, classe) {
    var div = document.createElement("div");
    div.className = "ajuda-msg " + classe;
    div.textContent = texto;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return div;
  }

  fab.addEventListener("click", function () { abrir(painel.hidden); });
  if (fechar) fechar.addEventListener("click", function () { abrir(false); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !painel.hidden) abrir(false);
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (ocupado) return;
    var pergunta = (input.value || "").trim();
    if (!pergunta) return;

    bolha(pergunta, "ajuda-user");
    historico.push({ role: "user", content: pergunta });
    input.value = "";
    ocupado = true;
    if (enviar) enviar.disabled = true;
    var carregando = bolha("…", "ajuda-bot ajuda-loading");

    fetch("/ajuda/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify({ pergunta: pergunta, historico: historico.slice(-6) })
    })
      .then(function (r) { return r.ok ? r.json() : { ok: false, resposta: "Erro de conexão." }; })
      .then(function (d) {
        carregando.remove();
        var resp = (d && d.resposta) || "Não consegui responder.";
        bolha(resp, "ajuda-bot");
        if (d && d.ok) historico.push({ role: "assistant", content: resp });
      })
      .catch(function () {
        carregando.remove();
        bolha("Falha ao falar com o assistente. Tente de novo.", "ajuda-bot");
      })
      .then(function () {
        ocupado = false;
        if (enviar) enviar.disabled = false;
        input.focus();
      });
  });
})();
