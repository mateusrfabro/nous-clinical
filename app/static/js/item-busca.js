// Busca/filtra a lista de itens no atendimento (req. do sócio: lista
// expansível com busca). CSP-safe, sem inline. Progressive enhancement.
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    var inp = document.querySelector("[data-filtra-itens]");
    if (!inp) return;
    var lista = document.querySelector("[data-itens-lista]");
    if (!lista) return;
    var itens = lista.querySelectorAll(".check-item");
    var vazio = lista.querySelector(".item-busca-vazio");
    inp.addEventListener("input", function () {
      var q = inp.value.trim().toLowerCase();
      var visiveis = 0;
      itens.forEach(function (it) {
        var nome = it.getAttribute("data-item-nome") || "";
        var mostra = !q || nome.indexOf(q) !== -1;
        it.hidden = !mostra;
        if (mostra) visiveis++;
      });
      if (vazio) vazio.hidden = visiveis !== 0;
    });
  });
})();
