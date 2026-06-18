/* auth-net.js — tela de login:
 *  (1) botão mostrar/ocultar senha (aria-pressed);
 *  (2) rede de nós animada no painel da marca (evoca o símbolo do Nous).
 *
 * CSP-safe: sem style/handler inline; canvas via API 2D. No-op se não houver
 * os elementos. Cores 100% derivadas dos tokens --brand-*-rgb => no portal
 * white-label a rede inteira (nós + linhas) assume a cor da clínica.
 * Pausa quando oculto (mobile/aba inativa) e respeita prefers-reduced-motion
 * em tempo de execução.
 */
(function () {
  "use strict";

  // ---- (1) mostrar/ocultar senha ----
  var toggles = document.querySelectorAll("[data-toggle-senha]");
  Array.prototype.forEach.call(toggles, function (btn) {
    btn.addEventListener("click", function () {
      var alvo = document.getElementById(btn.getAttribute("data-toggle-senha"));
      if (!alvo) return;
      var mostrar = alvo.type === "password";
      alvo.type = mostrar ? "text" : "password";
      btn.classList.toggle("is-on", mostrar);
      btn.setAttribute("aria-pressed", String(mostrar));
      btn.setAttribute("aria-label", mostrar ? "Ocultar senha" : "Mostrar senha");
    });
  });

  // ---- (2) rede de nós ----
  var canvas = document.getElementById("auth-net");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");
  if (!ctx) return;                       // contexto indisponível -> aborta

  var nodes = [], W = 0, H = 0, t = 0, raf = null;
  var primRgb = "67,184,165", accentRgb = "183,167,245", ACCENTS = [];
  var reduce = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;

  function lerCores() {
    var cs = getComputedStyle(document.body);
    function tok(n, fb) { return (cs.getPropertyValue(n) || "").trim() || fb; }
    primRgb = tok("--brand-primary-rgb", "67,184,165");
    accentRgb = tok("--brand-accent-rgb", "183,167,245");
    ACCENTS = ["rgb(" + primRgb + ")", "rgb(" + accentRgb + ")", "#6FB59C"];
  }

  function resize() {
    var r = canvas.getBoundingClientRect();
    W = r.width; H = r.height;
    if (!W || !H) return false;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);   // recalc a cada resize
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var alvo = Math.max(24, Math.min(64, Math.round((W * H) / 16000)));
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
    return true;
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
          ctx.strokeStyle = "rgba(" + primRgb + "," + (0.14 * (1 - d / 130)) + ")";
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }
    }
    for (var k = 0; k < nodes.length; k++) {
      var n = nodes[k];
      var pulse = n.cor ? (1 + 0.35 * Math.sin(t * 1.6 + n.ph)) : 1;
      if (n.cor) { ctx.shadowColor = n.cor; ctx.shadowBlur = 12; ctx.fillStyle = n.cor; }
      else { ctx.shadowBlur = 0; ctx.fillStyle = "rgba(" + primRgb + ",0.42)"; }
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r * pulse, 0, 6.2832); ctx.fill();
    }
    ctx.shadowBlur = 0;
    raf = requestAnimationFrame(frame);
  }

  function visivel() {
    if (reduce && reduce.matches) return false;       // reduzir movimento
    if (document.hidden) return false;                 // aba inativa
    var r = canvas.getBoundingClientRect();            // oculto no mobile = 0x0
    return r.width > 0 && r.height > 0;
  }
  function start() {
    if (raf !== null || !visivel()) return;
    lerCores();
    if (!resize()) return;
    raf = requestAnimationFrame(frame);
  }
  function stop() { if (raf !== null) { cancelAnimationFrame(raf); raf = null; } }
  function avaliar() { if (visivel()) start(); else stop(); }

  window.addEventListener("resize", function () { if (raf !== null) resize(); else avaliar(); });
  document.addEventListener("visibilitychange", avaliar);
  function ouvir(mq) { if (!mq) return; if (mq.addEventListener) mq.addEventListener("change", avaliar); else if (mq.addListener) mq.addListener(avaliar); }
  ouvir(reduce);
  if (window.matchMedia) ouvir(window.matchMedia("(max-width: 860px)"));

  start();
})();
