/* agenda-week.js — posiciona os blocos da agenda semanal via data-*.
 *
 * CSP-safe: lê data-top/height/left/width/accent e aplica em element.style
 * (não usa atributo style= inline no HTML). No-op se a página não tiver grade.
 */
(function () {
  "use strict";

  // Altura total da grade (gutter de horas + colunas dos dias).
  var grids = document.querySelectorAll("[data-grid-height]");
  Array.prototype.forEach.call(grids, function (el) {
    var h = parseInt(el.dataset.gridHeight, 10);
    if (h > 0) el.style.height = h + "px";
  });

  var eventos = document.querySelectorAll(".ag-event");
  Array.prototype.forEach.call(eventos, function (el) {
    var top = parseFloat(el.dataset.top);
    var height = parseFloat(el.dataset.height);
    var left = parseFloat(el.dataset.left);
    var width = parseFloat(el.dataset.width);
    var accent = el.dataset.accent;

    if (!isNaN(top)) el.style.top = top + "px";
    if (!isNaN(height)) el.style.height = height + "px";
    if (!isNaN(left)) el.style.left = "calc(" + left + "% + 2px)";
    if (!isNaN(width)) el.style.width = "calc(" + width + "% - 4px)";
    // Cor da BORDA = status (via classe CSS .ag-event.tag-*). O accent do
    // profissional vira o pontinho colorido (útil na visão "Todos").
    if (accent) {
      var dot = el.querySelector(".ag-ev-dot");
      if (dot) dot.style.backgroundColor = accent;
    }
  });
})();
