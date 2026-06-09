// Preview ao vivo da cor de marca livre (white-label v2b). Ao mexer no seletor
// de cor, aplica nos tokens do <body> via CSSOM (setProperty) — CSP-safe, igual
// ao agenda-week.js. O valor exato (com contraste derivado) é calculado no
// servidor quando salva; aqui é só pré-visualização.
(function () {
  "use strict";
  function rgb(hex) {
    var s = hex.replace("#", "");
    return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16),
            parseInt(s.slice(4, 6), 16)];
  }
  function lum(c) {
    var a = c.map(function (v) {
      v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
  }
  function hx(v) { return ("0" + Math.round(v).toString(16)).slice(-2); }
  function aplica(hex) {
    var c = rgb(hex), b = document.body;
    b.style.setProperty("--brand-verde-claro", hex);
    b.style.setProperty("--brand-primary-rgb", c.join(", "));
    b.style.setProperty("--primary-dark", "#" + c.map(function (v) { return hx(v * 0.84); }).join(""));
    b.style.setProperty("--text-on-ouro", lum(c) > 0.4 ? "#1E293B" : "#F8FAF8");
  }
  document.addEventListener("DOMContentLoaded", function () {
    var inp = document.querySelector("[data-cor-preview]");
    if (!inp) return;
    inp.addEventListener("input", function () { aplica(inp.value); });
  });
})();
