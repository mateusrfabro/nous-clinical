// Máscara de telefone BR: (XX) XXXXX-XXXX (celular) ou (XX) XXXX-XXXX (fixo).
// Aplica em todo input[type=tel]. CSP-safe (sem inline). Progressive
// enhancement: sem JS o campo segue funcionando como texto livre.
(function () {
  "use strict";
  function formata(v) {
    var d = (v || "").replace(/\D/g, "").slice(0, 11);
    if (d.length === 0) return "";
    if (d.length <= 2) return "(" + d;
    if (d.length <= 6) return "(" + d.slice(0, 2) + ") " + d.slice(2);
    if (d.length <= 10)
      return "(" + d.slice(0, 2) + ") " + d.slice(2, 6) + "-" + d.slice(6);
    return "(" + d.slice(0, 2) + ") " + d.slice(2, 7) + "-" + d.slice(7);
  }
  function liga(inp) {
    inp.addEventListener("input", function () {
      var pos = inp.selectionStart;
      var antes = inp.value.length;
      inp.value = formata(inp.value);
      // mantém o cursor estável ao digitar no fim
      if (pos >= antes) inp.setSelectionRange(inp.value.length, inp.value.length);
    });
    if (inp.value) inp.value = formata(inp.value);
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll('input[type="tel"]').forEach(liga);
  });
})();
