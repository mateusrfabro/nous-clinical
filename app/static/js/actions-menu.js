/* actions-menu.js — popover "⋯ Mais" para ações secundárias de linha/card.
 *
 * CSP-safe: nada inline. Delegação no document. Abre/fecha o menu irmão do
 * botão [data-actions-toggle]; gerencia foco e teclado (WCAG):
 *  - ao abrir, foca o 1º item; Esc fecha e devolve o foco ao toggle.
 *  - ↑/↓ navegam, Home/End vão ao primeiro/último item.
 *  - clique fora / scroll / resize fecham. Um menu aberto por vez.
 * No-op se a página não tiver menus.
 */
(function () {
  "use strict";

  function itens(menu) {
    return Array.prototype.slice.call(
      menu.querySelectorAll("a[href], button:not([disabled])"));
  }

  function fecha(menu, focoNoToggle) {
    if (!menu || menu.hidden) return;
    menu.hidden = true;
    var toggle = menu.parentNode &&
      menu.parentNode.querySelector("[data-actions-toggle]");
    if (toggle) {
      toggle.setAttribute("aria-expanded", "false");
      if (focoNoToggle) toggle.focus();
    }
  }

  function fechaTodos(exceto) {
    var abertos = document.querySelectorAll(".actions-more-menu:not([hidden])");
    Array.prototype.forEach.call(abertos, function (m) {
      if (m !== exceto) fecha(m, false);
    });
  }

  function posiciona(toggle, menu) {
    // Menu é position:fixed — ancora ao botão e mantém dentro da viewport.
    var r = toggle.getBoundingClientRect();
    var mw = menu.offsetWidth, mh = menu.offsetHeight;
    var left = Math.max(8, Math.min(r.right - mw, window.innerWidth - mw - 8));
    var top = r.bottom + 4;
    if (top + mh > window.innerHeight - 8 && r.top - mh - 4 > 8) {
      top = r.top - mh - 4;   // abre pra cima se não couber embaixo
    }
    menu.style.left = left + "px";
    menu.style.top = top + "px";
  }

  function abre(toggle, menu) {
    fechaTodos(menu);
    menu.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    posiciona(toggle, menu);
    var its = itens(menu);
    if (its.length) its[0].focus();   // foco vai pro 1º item
  }

  document.addEventListener("click", function (ev) {
    var t = ev.target;
    if (!(t instanceof Element)) return;
    var toggle = t.closest("[data-actions-toggle]");
    if (toggle) {
      ev.preventDefault();
      var menu = toggle.parentNode.querySelector(".actions-more-menu");
      if (!menu) return;
      if (menu.hidden) abre(toggle, menu); else fecha(menu, true);
      return;
    }
    // Clique fora de qualquer menu fecha tudo (deixa o clique no item agir).
    if (!t.closest(".actions-more-menu")) fechaTodos(null);
  });

  document.addEventListener("keydown", function (ev) {
    var t = ev.target;
    if (!(t instanceof Element)) return;

    var menu = t.closest(".actions-more-menu");
    if (menu && !menu.hidden) {
      var its = itens(menu);
      var i = its.indexOf(t);
      if (ev.key === "ArrowDown") {
        ev.preventDefault();
        if (its.length) its[(i + 1) % its.length].focus();
      } else if (ev.key === "ArrowUp") {
        ev.preventDefault();
        if (its.length) its[(i - 1 + its.length) % its.length].focus();
      } else if (ev.key === "Home") {
        ev.preventDefault();
        if (its.length) its[0].focus();
      } else if (ev.key === "End") {
        ev.preventDefault();
        if (its.length) its[its.length - 1].focus();
      } else if (ev.key === "Escape") {
        ev.preventDefault();
        fecha(menu, true);
      }
      return;
    }

    var tog = t.closest("[data-actions-toggle]");
    if (tog && ev.key === "ArrowDown") {
      ev.preventDefault();
      var m = tog.parentNode.querySelector(".actions-more-menu");
      if (m && m.hidden) abre(tog, m);
    } else if (ev.key === "Escape") {
      fechaTodos(null);
    }
  });

  // Menu aberto + scroll/resize: fecha (fixed descolaria do botão).
  window.addEventListener("scroll", function () { fechaTodos(null); }, true);
  window.addEventListener("resize", function () { fechaTodos(null); });
})();
