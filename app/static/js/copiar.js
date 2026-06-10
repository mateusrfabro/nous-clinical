// Botão "Copiar" CSP-safe: copia o valor do input referenciado em data-copiar.
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-copiar]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var alvo = document.getElementById(btn.getAttribute("data-copiar"));
        if (!alvo) return;
        var txt = alvo.value || alvo.textContent || "";
        var feito = function () {
          var orig = btn.textContent;
          btn.textContent = "Copiado!";
          setTimeout(function () { btn.textContent = orig; }, 1500);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(txt).then(feito).catch(function () {
            alvo.select(); document.execCommand("copy"); feito();
          });
        } else {
          alvo.select(); document.execCommand("copy"); feito();
        }
      });
    });
  });
})();
