// Autopreenchimento de endereço por CEP. Chama nosso proxy backend
// (/pacientes/cep/<cep>) — mantém a CSP estrita (connect-src 'self').
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    var cep = document.getElementById("cep");
    if (!cep) return;
    var endereco = document.getElementById("endereco");
    var bairro = document.getElementById("bairro");
    var cidade = document.getElementById("cidade");

    function buscar() {
      var d = (cep.value || "").replace(/\D/g, "");
      if (d.length !== 8) return;
      fetch("/pacientes/cep/" + d, { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          if (!j || j.erro) return;
          // só preenche o que estiver vazio (não sobrescreve digitação)
          if (endereco && !endereco.value) endereco.value = j.endereco || "";
          if (bairro && !bairro.value) bairro.value = j.bairro || "";
          if (cidade && !cidade.value) cidade.value = j.cidade || "";
        })
        .catch(function () { /* silencioso: form segue manual */ });
    }
    cep.addEventListener("blur", buscar);
  });
})();
