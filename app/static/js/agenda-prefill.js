// Agenda: ao escolher o profissional, puxa a sala e a duração padrão dele
// pro formulário (req. do sócio). CSP-safe (sem inline). Só age no change do
// usuário — não sobrescreve valores já salvos ao abrir a tela de reagendar.
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    var sel = document.querySelector("[data-prof-select]");
    if (!sel) return;
    var salaInput = document.querySelector("[data-prof-sala]");
    var duracaoSel = document.querySelector("[data-prof-duracao]");
    sel.addEventListener("change", function () {
      var opt = sel.options[sel.selectedIndex];
      if (!opt) return;
      var sala = opt.getAttribute("data-sala") || "";
      var dur = opt.getAttribute("data-duracao") || "";
      if (salaInput) salaInput.value = sala;
      if (duracaoSel && dur) {
        for (var i = 0; i < duracaoSel.options.length; i++) {
          if (duracaoSel.options[i].value === dur) { duracaoSel.selectedIndex = i; break; }
        }
      }
    });
  });
})();
