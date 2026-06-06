/* Toasts (CSP-safe, sem handlers inline).
 *
 * Promove o .flash-container renderizado pelo servidor a uma pilha flutuante
 * com botao de fechar e auto-dismiss. Erros NAO somem sozinhos (o usuario
 * precisa ler); sucesso/info/aviso somem apos alguns segundos.
 *
 * Progressive enhancement: sem JS, o flash continua sendo um alerta normal.
 */
(function () {
  "use strict";

  var AUTO_MS = 5000;          // sucesso/info/aviso
  var reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function dismiss(alert) {
    if (!alert || alert.dataset.dismissing) return;
    alert.dataset.dismissing = "1";
    if (reduce) { remove(alert); return; }
    alert.classList.add("toast-out");
    var done = false;
    var fin = function () { if (!done) { done = true; remove(alert); } };
    alert.addEventListener("animationend", fin, { once: true });
    window.setTimeout(fin, 300);   // fallback se animationend nao disparar
  }

  function remove(alert) {
    var box = alert.parentNode;
    if (alert.parentNode) alert.parentNode.removeChild(alert);
    if (box && box.classList.contains("flash-container") &&
        box.querySelectorAll(".alert").length === 0) {
      box.parentNode && box.parentNode.removeChild(box);
    }
  }

  function enhance(box) {
    box.classList.add("is-toast");
    var alerts = box.querySelectorAll(".alert");
    Array.prototype.forEach.call(alerts, function (alert) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "toast-close";
      btn.setAttribute("aria-label", "Fechar");
      btn.textContent = "×";     // ×
      btn.addEventListener("click", function () { dismiss(alert); });
      alert.appendChild(btn);

      var isError = alert.classList.contains("alert-error");
      if (!isError) {
        window.setTimeout(function () { dismiss(alert); }, AUTO_MS);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var boxes = document.querySelectorAll(".flash-container");
    Array.prototype.forEach.call(boxes, enhance);
  });
})();
