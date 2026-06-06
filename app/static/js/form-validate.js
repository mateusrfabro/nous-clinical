/* Validação inline de formulários (CSP-safe, sem handlers inline).
 *
 * Usa a Constraint Validation API nativa (required, type=email, pattern,
 * minlength...) e mostra a mensagem embaixo do campo, em PT-BR, em vez do
 * balão nativo. Progressive enhancement: sem JS, a validação nativa do
 * browser continua valendo (não setamos novalidate no HTML, só via JS).
 *
 * Opt-out: <form data-no-validate> não é processado.
 */
(function () {
  "use strict";

  var MSGS = {
    valueMissing: "Campo obrigatório.",
    typeMismatch: "Formato inválido.",
    patternMismatch: "Formato inválido.",
    tooShort: "Muito curto.",
    tooLong: "Muito longo.",
    rangeUnderflow: "Valor abaixo do mínimo.",
    rangeOverflow: "Valor acima do máximo.",
    stepMismatch: "Valor inválido.",
    badInput: "Valor inválido."
  };

  function mensagem(campo) {
    var v = campo.validity;
    for (var k in MSGS) {
      if (v[k]) {
        if (k === "typeMismatch" && campo.type === "email") {
          return "E-mail inválido.";
        }
        return MSGS[k];
      }
    }
    return campo.validationMessage || "Valor inválido.";
  }

  function alvoErro(campo) {
    // O .field-error vai depois do campo (ou do .form-group que o contém).
    return campo.closest(".form-group") || campo.parentNode;
  }

  function limpar(campo) {
    campo.classList.remove("is-invalid");
    campo.removeAttribute("aria-invalid");
    var box = alvoErro(campo);
    var err = box && box.querySelector(".field-error");
    if (err) err.parentNode.removeChild(err);
  }

  function marcar(campo) {
    campo.classList.add("is-invalid");
    campo.setAttribute("aria-invalid", "true");
    var box = alvoErro(campo);
    if (!box) return;
    var err = box.querySelector(".field-error");
    if (!err) {
      err = document.createElement("span");
      err.className = "field-error";
      err.setAttribute("role", "alert");
      box.appendChild(err);
    }
    err.textContent = mensagem(campo);
  }

  function valida(campo) {
    if (!campo.willValidate) return true;
    if (campo.checkValidity()) { limpar(campo); return true; }
    marcar(campo);
    return false;
  }

  function liga(form) {
    if (form.hasAttribute("data-no-validate")) return;
    form.noValidate = true;   // assume controle das mensagens (só com JS)

    // Revalida ao sair/editar o campo (feedback imediato, sem ser intrusivo).
    form.addEventListener("blur", function (e) {
      if (e.target.willValidate) valida(e.target);
    }, true);
    form.addEventListener("input", function (e) {
      if (e.target.classList.contains("is-invalid")) valida(e.target);
    });
  }

  // Submit em CAPTURE no document: roda ANTES do form-submitting.js (loading).
  // Este arquivo é carregado antes do form-submitting.js, então registra antes
  // e o stopImmediatePropagation barra o loading quando há campo inválido.
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form || form.tagName !== "FORM") return;
    if (form.hasAttribute("data-no-validate")) return;
    var primeiro = null;
    var campos = form.querySelectorAll("input, select, textarea");
    Array.prototype.forEach.call(campos, function (campo) {
      if (!valida(campo) && !primeiro) primeiro = campo;
    });
    if (primeiro) {
      e.preventDefault();
      e.stopImmediatePropagation();   // barra o loading do form-submitting.js
      primeiro.focus();
    }
  }, true);

  document.addEventListener("DOMContentLoaded", function () {
    var forms = document.querySelectorAll("form");
    Array.prototype.forEach.call(forms, liga);
  });
})();
