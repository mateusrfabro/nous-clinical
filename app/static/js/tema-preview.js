// Preview ao vivo do tema (white-label): ao marcar uma opção, troca a classe
// tema-* do <body> pra recolorir a tela inteira antes de salvar. CSP-safe.
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    var radios = document.querySelectorAll("[data-tema-radio]");
    if (!radios.length) return;
    var body = document.body;
    radios.forEach(function (r) {
      r.addEventListener("change", function () {
        body.className = (body.className.replace(/\btema-[\w-]+\b/g, "").trim()
                          + " tema-" + r.value).trim();
        document.querySelectorAll(".tema-opcao").forEach(function (o) {
          o.classList.remove("is-sel");
        });
        var lab = r.closest(".tema-opcao");
        if (lab) lab.classList.add("is-sel");
      });
    });
  });
})();
