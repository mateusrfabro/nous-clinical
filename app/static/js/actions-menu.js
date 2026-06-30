/* actions-menu.js — popover "⋯ Mais" para ações secundárias de linha/card.
 *
 * CSP-safe: nada inline. Delegação no document. Abre/fecha o menu irmão do
 * botão [data-actions-toggle]; fecha ao clicar fora ou apertar Esc. No-op se a
 * página não tiver menus. Um menu aberto por vez.
 */
(function () {
  "use strict";

  function fechaTodos(exceto) {
    var abertos = document.querySelectorAll(".actions-more-menu:not([hidden])");
    Array.prototype.forEach.call(abertos, function (menu) {
      if (menu === exceto) return;
      menu.hidden = true;
      var t = menu.parentNode &&
        menu.parentNode.querySelector("[data-actions-toggle]");
      if (t) t.setAttribute("aria-expanded", "false");
    });
  }

  document.addEventListener("click", function (ev) {
    var toggle = ev.target.closest("[data-actions-toggle]");
    if (toggle) {
      ev.preventDefault();
      var menu = toggle.parentNode.querySelector(".actions-more-menu");
      if (!menu) return;
      var vaiAbrir = menu.hidden;
      fechaTodos(vaiAbrir ? menu : null);
      menu.hidden = !vaiAbrir;
      toggle.setAttribute("aria-expanded", vaiAbrir ? "true" : "false");
      return;
    }
    // Clique fora de qualquer menu fecha tudo (deixa o clique no item agir).
    if (!ev.target.closest(".actions-more-menu")) fechaTodos(null);
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") fechaTodos(null);
  });
})();
