/* auth-net.js — tela de login:
 *  (1) rede de nós animada no painel da marca (evoca o símbolo do Nous);
 *  (2) botão mostrar/ocultar senha.
 *
 * CSP-safe: sem style inline no HTML; posições do canvas via API 2D e
 * dimensões via atributos. No-op se a página não tiver os elementos.
 * As cores dos nós vêm dos tokens --brand-* => no portal white-label a
 * animação assume a cor da clínica automaticamente.
 */
(function () {
  "use strict";

  // ---- (2) mostrar/ocultar senha ----
  var toggles = document.querySelectorAll("[data-toggle-senha]");
  Array.prototype.forEach.call(toggles, function (btn) {
    btn.addEventListener("click", function () {
      var alvo = document.getElementById(btn.getAttribute("data-toggle-senha"));
      if (!alvo) return;
      var mostrar = alvo.type === "password";
      alvo.type = mostrar ? "text" : "password";
      btn.classList.toggle("is-on", mostrar);
      btn.setAttribute("aria-label", mostrar ? "Ocultar senha" : "Mostrar senha");
    });
  });

  // ---- (1) rede de nós ----
  var canvas = document.getElementById("auth-net");
  if (!canvas || !canvas.getContext) return;
  if (window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  var ctx = canvas.getContext("2d");
  var dpr = Math.min(window.devicePixelRatio || 1, 2);
  var nodes = [], W = 0, H = 0, t = 0;

  var cs = getComputedStyle(document.body);
  function tok(nome, fb) {
    var v = (cs.getPropertyValue(nome) || "").trim();
    return v || fb;
  }
  // primária + accent do tema da clínica + sage (cor do símbolo Nous).
  var ACCENTS = [
    tok("--brand-verde-claro", "#43B8A5"),
    tok("--brand-ouro", "#B7A7F5"),
    "#6FB59C"
  ];

  function resize() {
    var r = canvas.getBoundingClientRect();
    W = r.width; H = r.height;
    if (!W || !H) return;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var alvo = Math.round((W * H) / 16000);
    alvo = Math.max(24, Math.min(64, alvo));
    nodes = [];
    for (var i = 0; i < alvo; i++) {
      nodes.push({
        x: Math.random() * W, y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.22, vy: (Math.random() - 0.5) * 0.22,
        r: Math.random() * 1.7 + 1.1,
        cor: Math.random() < 0.22 ? ACCENTS[(Math.random() * ACCENTS.length) | 0] : null,
        ph: Math.random() * 6.28
      });
    }
  }

  function frame() {
    t += 0.016;
    ctx.clearRect(0, 0, W, H);
    for (var i = 0; i < nodes.length; i++) {
      var a = nodes[i];
      a.x += a.vx; a.y += a.vy;
      if (a.x < 0 || a.x > W) a.vx *= -1;
      if (a.y < 0 || a.y > H) a.vy *= -1;
      for (var j = i + 1; j < nodes.length; j++) {
        var b = nodes[j], dx = a.x - b.x, dy = a.y - b.y;
        var d = Math.sqrt(dx * dx + dy * dy);
        if (d < 130) {
          ctx.strokeStyle = "rgba(120,190,178," + (0.16 * (1 - d / 130)) + ")";
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }
    }
    for (var k = 0; k < nodes.length; k++) {
      var n = nodes[k];
      var pulse = n.cor ? (1 + 0.35 * Math.sin(t * 1.6 + n.ph)) : 1;
      if (n.cor) { ctx.shadowColor = n.cor; ctx.shadowBlur = 12; ctx.fillStyle = n.cor; }
      else { ctx.shadowBlur = 0; ctx.fillStyle = "rgba(160,200,194,0.5)"; }
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r * pulse, 0, 6.2832); ctx.fill();
    }
    ctx.shadowBlur = 0;
    requestAnimationFrame(frame);
  }

  window.addEventListener("resize", resize);
  resize();
  requestAnimationFrame(frame);
})();
