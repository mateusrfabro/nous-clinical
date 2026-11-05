/* agenda-kanban.js — arrastar-soltar cards entre colunas de status (v2).
 *
 * Progressive enhancement: sem JS, os botões de ação rápida do card continuam
 * movendo a consulta (POST normal). Com JS, arrastar um card para outra coluna
 * posta no mesmo endpoint (agenda.mudar_status, auditado) via fetch e move o
 * card na hora (otimista). No-op se a página não for o quadro Kanban.
 *
 * CSP-safe: sem handlers inline; tudo via addEventListener e data-*.
 *
 * Limitação conhecida (v2): após o drop, os RÓTULOS das ações rápidas do card
 * podem ficar momentaneamente desatualizados (ex.: card movido p/ "Confirmado"
 * ainda mostrar "Confirmar"); qualquer clique/navegação ressincroniza com o
 * servidor. A coluna 'Atendido' não é alvo de drop (status não é manual).
 */
(function () {
  "use strict";

  var board = document.querySelector("[data-kanban-board]");
  if (!board) return;
  var csrf = board.dataset.csrf || "";
  var dragging = null;

  // Neutraliza o drag nativo dos elementos internos (links/botões/inputs): sem
  // isto, em alguns browsers grb num link inicia o arraste DELE, não do card.
  Array.prototype.forEach.call(
    board.querySelectorAll("[data-kanban-card] a, [data-kanban-card] button," +
                           " [data-kanban-card] select, [data-kanban-card] input"),
    function (el) { el.setAttribute("draggable", "false"); }
  );

  function bodies() {
    return board.querySelectorAll("[data-kanban-drop]");
  }

  function updateCounts() {
    var cols = board.querySelectorAll(".kanban-col");
    Array.prototype.forEach.call(cols, function (col) {
      var body = col.querySelector(".kanban-col-body");
      var count = col.querySelector("[data-kanban-count]");
      if (!body || !count) return;
      var n = body.querySelectorAll("[data-kanban-card]").length;
      count.textContent = String(n);
      syncPlaceholder(body, n);
    });
  }

  function syncPlaceholder(body, n) {
    var ph = body.querySelector(".kanban-empty");
    if (n === 0 && !ph) {
      var p = document.createElement("p");
      p.className = "kanban-empty muted text-sm";
      p.textContent = "—";
      body.appendChild(p);
    } else if (n > 0 && ph) {
      ph.parentNode.removeChild(ph);
    }
  }

  function onDragStart(ev) {
    if (!(ev.target instanceof Element)) return;
    var card = ev.target.closest("[data-kanban-card]");
    if (!card) return;
    dragging = card;
    card.classList.add("is-dragging");
    if (ev.dataTransfer) {
      ev.dataTransfer.effectAllowed = "move";
      // Alguns browsers exigem setData p/ iniciar o arrasto.
      ev.dataTransfer.setData("text/plain", card.dataset.agId || "");
    }
  }

  function onDragEnd() {
    if (dragging) dragging.classList.remove("is-dragging");
    dragging = null;
    Array.prototype.forEach.call(bodies(), function (b) {
      b.classList.remove("is-drop-over");
    });
  }

  function onDragOver(ev) {
    if (!dragging) return;
    ev.preventDefault();           // permite o drop
    if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
    this.classList.add("is-drop-over");
  }

  function onDragLeave() {
    this.classList.remove("is-drop-over");
  }

  function onDrop(ev) {
    ev.preventDefault();
    this.classList.remove("is-drop-over");
    if (!dragging) return;
    var card = dragging;
    var destino = this.dataset.status;
    var origem = card.dataset.status;
    if (!destino || destino === origem) return;   // mesma coluna = no-op

    // Move otimista: posiciona o card na coluna alvo já.
    var origemBody = card.parentNode;
    this.appendChild(card);
    card.dataset.status = destino;
    updateCounts();

    var body = "csrf_token=" + encodeURIComponent(csrf) +
               "&status=" + encodeURIComponent(destino);
    fetch(card.dataset.moveUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": csrf
      },
      body: body,
      credentials: "same-origin"
    }).then(function (res) {
      if (!res.ok) throw new Error("status " + res.status);
      // Sucesso: o servidor já persistiu/auditou. Mantém a posição otimista.
    }).catch(function () {
      // Falha: devolve o card à origem e recarrega p/ estado consistente.
      if (origemBody) origemBody.appendChild(card);
      card.dataset.status = origem;
      updateCounts();
      window.location.reload();
    });
  }

  // Liga os listeners.
  board.addEventListener("dragstart", onDragStart);
  board.addEventListener("dragend", onDragEnd);
  Array.prototype.forEach.call(bodies(), function (b) {
    b.addEventListener("dragover", onDragOver);
    b.addEventListener("dragleave", onDragLeave);
    b.addEventListener("drop", onDrop);
  });
})();
