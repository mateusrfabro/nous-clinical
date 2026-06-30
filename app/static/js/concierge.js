/* Concierge IA — gera o rascunho da mensagem de retorno/reativação e monta o
   link de WhatsApp a partir do texto (que a recepção pode editar antes de enviar).
   CSP-safe: sem handler inline. No-op se a página não tiver [data-concierge]. */
(function () {
  "use strict";
  var root = document.querySelector("[data-concierge]");
  if (!root) return;
  var url = root.getAttribute("data-concierge-url");
  var csrf = root.getAttribute("data-csrf") || "";

  function waLink(telefone, texto) {
    var d = (telefone || "").replace(/\D/g, "");
    if (!d) return null;
    if (d.length <= 11) d = "55" + d;   // sem DDI -> assume Brasil (espelha o servidor)
    return "https://wa.me/" + d + "?text=" + encodeURIComponent(texto || "");
  }

  function boxFor(id) {
    return root.querySelector('.concierge-box[data-box-for="' + id + '"]');
  }

  function atualizaWa(box) {
    var ta = box.querySelector(".concierge-text");
    var wa = box.querySelector(".concierge-wa");
    if (!ta || !wa) return;
    var link = waLink(box.getAttribute("data-telefone"), ta.value);
    if (link && ta.value.trim()) { wa.href = link; wa.hidden = false; }
    else { wa.hidden = true; }
  }

  function gerar(box, btn) {
    var ta = box.querySelector(".concierge-text");
    if (!ta) return;
    var id = box.getAttribute("data-box-for");
    var motivo = box.getAttribute("data-motivo") || "retorno";
    box.hidden = false;
    ta.value = "Gerando mensagem…";
    ta.disabled = true;
    if (btn) btn.disabled = true;
    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify({
        paciente_id: parseInt(id, 10), motivo: motivo, canal: "whatsapp"
      })
    })
      .then(function (r) {
        return r.ok ? r.json() : { ok: false, texto: "Erro de conexão." };
      })
      .then(function (d) {
        ta.disabled = false;
        ta.value = (d && d.texto) || "Não consegui gerar a mensagem.";
        atualizaWa(box);
        ta.focus();
      })
      .catch(function () {
        ta.disabled = false;
        ta.value = "Falha ao gerar. Tente de novo.";
      })
      .then(function () { if (btn) btn.disabled = false; });
  }

  function copiar(box) {
    var ta = box.querySelector(".concierge-text");
    var btn = box.querySelector(".concierge-copy");
    if (!ta) return;
    var done = function () {
      if (!btn) return;
      var antes = btn.textContent;
      btn.textContent = "Copiado ✓";
      setTimeout(function () { btn.textContent = antes; }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(ta.value).then(done, function () {
        ta.select(); document.execCommand("copy"); done();
      });
    } else {
      ta.select(); document.execCommand("copy"); done();
    }
  }

  root.addEventListener("click", function (e) {
    var gen = e.target.closest(".concierge-gen");
    if (gen && root.contains(gen)) {
      e.preventDefault();
      var box = boxFor(gen.getAttribute("data-target"));
      if (box) gerar(box, gen);
      return;
    }
    var regen = e.target.closest(".concierge-regen");
    if (regen && root.contains(regen)) {
      e.preventDefault();
      gerar(regen.closest(".concierge-box"), regen);
      return;
    }
    var copy = e.target.closest(".concierge-copy");
    if (copy && root.contains(copy)) {
      e.preventDefault();
      copiar(copy.closest(".concierge-box"));
    }
  });

  root.addEventListener("input", function (e) {
    if (e.target.classList.contains("concierge-text")) {
      atualizaWa(e.target.closest(".concierge-box"));
    }
  });
})();
