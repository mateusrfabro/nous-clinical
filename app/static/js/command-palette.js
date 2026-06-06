/* command-palette.js — busca rápida / navegação (Ctrl+K). CSP-safe.
 *
 * Abre com Ctrl/Cmd+K ou clique no [data-cmdk]. Os comandos de navegação são
 * lidos da própria sidebar (já filtrada por papel), então respeitam permissão.
 * A busca de pacientes vai no endpoint /buscar (escopado por papel no servidor).
 * Sem handlers inline; DOM criado via createElement.
 */
(function () {
  "use strict";
  if (!document.body || !document.body.classList.contains("app")) return;

  var navCmds = [];
  Array.prototype.forEach.call(
    document.querySelectorAll(".sidebar-nav .nav-item, .sidebar-foot .nav-item"),
    function (a) {
      if (a.tagName !== "A" || !a.getAttribute("href")) return;
      var span = a.querySelector("span");
      var label = (span ? span.textContent : a.textContent || "").trim();
      if (label) navCmds.push({ label: label, sub: "Ir para", url: a.href });
    }
  );

  // --- monta o overlay (uma vez) ---
  var overlay = document.createElement("div");
  overlay.className = "cmdk-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "Busca rápida");
  overlay.hidden = true;

  var panel = document.createElement("div");
  panel.className = "cmdk-panel";
  var input = document.createElement("input");
  input.className = "cmdk-input";
  input.type = "text";
  input.setAttribute("placeholder", "Buscar paciente ou ir para…");
  input.setAttribute("aria-label", "Buscar");
  input.autocomplete = "off";
  var list = document.createElement("ul");
  list.className = "cmdk-list";
  list.setAttribute("role", "listbox");
  panel.appendChild(input);
  panel.appendChild(list);
  overlay.appendChild(panel);
  document.body.appendChild(overlay);

  var itens = [];   // [{label, sub, url}]
  var sel = 0;
  var seq = 0;      // descarta respostas fetch fora de ordem

  function abrir() {
    overlay.hidden = false;
    input.value = "";
    render(navCmds);
    window.setTimeout(function () { input.focus(); }, 0);
  }
  function fechar() { overlay.hidden = true; list.innerHTML = ""; }
  function aberta() { return !overlay.hidden; }

  function render(arr) {
    itens = arr;
    sel = 0;
    list.innerHTML = "";
    if (!arr.length) {
      var vazio = document.createElement("li");
      vazio.className = "cmdk-empty";
      vazio.textContent = "Nada encontrado.";
      list.appendChild(vazio);
      return;
    }
    arr.forEach(function (it, i) {
      var li = document.createElement("li");
      li.className = "cmdk-item" + (i === sel ? " is-sel" : "");
      li.setAttribute("role", "option");
      var lab = document.createElement("span");
      lab.className = "cmdk-label";
      lab.textContent = it.label;
      var sub = document.createElement("span");
      sub.className = "cmdk-sub";
      sub.textContent = it.sub || "";
      li.appendChild(lab);
      li.appendChild(sub);
      li.addEventListener("mouseenter", function () { mover(i); });
      li.addEventListener("click", function () { ir(i); });
      list.appendChild(li);
    });
  }

  function mover(i) {
    var nodes = list.querySelectorAll(".cmdk-item");
    if (!nodes.length) return;
    sel = (i + nodes.length) % nodes.length;
    Array.prototype.forEach.call(nodes, function (n, k) {
      n.classList.toggle("is-sel", k === sel);
    });
    nodes[sel].scrollIntoView({ block: "nearest" });
  }

  function ir(i) {
    var it = itens[i];
    if (it && it.url) window.location.href = it.url;
  }

  function filtrarNav(q) {
    q = q.toLowerCase();
    return navCmds.filter(function (c) {
      return c.label.toLowerCase().indexOf(q) !== -1;
    });
  }

  var timer = null;
  function onInput() {
    var q = input.value.trim();
    if (timer) window.clearTimeout(timer);
    if (q.length < 2) { render(filtrarNav(q)); return; }
    var nav = filtrarNav(q);
    var meu = ++seq;
    timer = window.setTimeout(function () {
      fetch("/buscar?q=" + encodeURIComponent(q), {
        headers: { "X-Requested-With": "XMLHttpRequest" }
      })
        .then(function (r) { return r.ok ? r.json() : { pacientes: [] }; })
        .then(function (data) {
          if (meu !== seq) return;   // resposta obsoleta
          var pac = (data.pacientes || []).map(function (p) {
            return { label: p.nome, sub: p.sub || "Paciente", url: p.url };
          });
          render(pac.concat(nav));
        })
        .catch(function () { if (meu === seq) render(nav); });
    }, 160);
  }

  input.addEventListener("input", onInput);
  input.addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown") { e.preventDefault(); mover(sel + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); mover(sel - 1); }
    else if (e.key === "Enter") { e.preventDefault(); ir(sel); }
    else if (e.key === "Escape") { e.preventDefault(); fechar(); }
    else if (e.key === "Tab") { e.preventDefault(); }  // foco preso no input
  });
  overlay.addEventListener("mousedown", function (e) {
    if (e.target === overlay) fechar();
  });

  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      aberta() ? fechar() : abrir();
    }
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-cmdk]"),
    function (btn) {
      btn.addEventListener("click", function (e) { e.preventDefault(); abrir(); });
    });
})();
