// Cadastro de Itens: alterna o campo "Valor" conforme o tipo escolhido no
// add unificado (Item faturável tem valor; Convênio não). CSP-safe (sem inline).
(function () {
  "use strict";
  function aplica(sel) {
    var form = sel.closest("form");
    if (!form) return;
    var valorWrap = form.querySelector("[data-item-valor]");
    if (!valorWrap) return;
    var ehConvenio = sel.value === "convenio";
    valorWrap.hidden = ehConvenio;
    var input = valorWrap.querySelector("input");
    if (input) input.disabled = ehConvenio;
  }
  document.addEventListener("DOMContentLoaded", function () {
    var sels = document.querySelectorAll("[data-item-tipo]");
    sels.forEach(function (sel) {
      aplica(sel);
      sel.addEventListener("change", function () { aplica(sel); });
    });
  });
})();
