/* gitmgf — progressive enhancement only. Every page works without this file. */
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  function onReady(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  // Confirm destructive actions: <form data-confirm="…"> or <button data-confirm="…">
  document.addEventListener("submit", function (event) {
    var form = event.target;
    var submitter = event.submitter;
    var message = (submitter && submitter.getAttribute("data-confirm")) || form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);

  // Certification claims: reveal detail fields only for checked items (server renders them all).
  function syncClaims(root) {
    root.querySelectorAll("[data-cert-claim]").forEach(function (box) {
      var toggle = box.querySelector("[data-cert-toggle]");
      if (!toggle) return;
      box.classList.toggle("is-on", toggle.checked);
    });
  }

  // MDR or IVDR switches CE on with the matching legal basis (PRD F20 coherence helper).
  function coherence(event) {
    var input = event.target;
    if (!input.matches || !input.matches("[data-cert-toggle]")) return;
    var code = input.getAttribute("data-cert-toggle");
    if ((code === "mdr" || code === "ivdr") && input.checked) {
      var ce = document.querySelector('[data-cert-toggle="ce"]');
      if (ce && !ce.checked) ce.checked = true;
      var basis = document.querySelector('[name="cert_ce__legal_basis"]');
      if (basis && !basis.value) basis.value = code === "mdr" ? "MDR" : "IVDR";
    }
    syncClaims(document);
  }

  // Sort <select> outside the search form still drives the form.
  function bindAutoSubmit(root) {
    root.querySelectorAll("[data-autosubmit]").forEach(function (el) {
      if (el.dataset.bound) return;
      el.dataset.bound = "1";
      el.addEventListener("change", function () {
        var form = el.form || document.getElementById(el.getAttribute("form"));
        if (!form) return;
        if (form.requestSubmit) form.requestSubmit(); else form.submit();
      });
    });
  }

  // Hide the "Pesquisar" submit when live search is available.
  function liveSearch(root) {
    root.querySelectorAll("[data-live-hide]").forEach(function (el) { el.classList.add("visually-hidden"); });
  }

  // Tag suggestions (HTMX chips under the tags field): clicking one appends it to the input.
  document.addEventListener("click", function (event) {
    var chip = event.target.closest && event.target.closest("[data-tag-suggestion]");
    if (!chip) return;
    var input = document.getElementById("f-tags");
    if (!input) return;
    var parts = input.value.split(",").map(function (p) { return p.trim(); }).filter(Boolean);
    parts.pop();
    parts.push(chip.getAttribute("data-tag-suggestion"));
    input.value = parts.join(", ") + ", ";
    input.focus();
    var box = document.getElementById("tag-suggestions");
    if (box) box.innerHTML = "";
  });

  onReady(function () {
    syncClaims(document);
    bindAutoSubmit(document);
    liveSearch(document);
    document.addEventListener("change", coherence);
    // Close open <details class="menu"> when clicking elsewhere.
    document.addEventListener("click", function (event) {
      document.querySelectorAll("details.menu[open]").forEach(function (menu) {
        if (!menu.contains(event.target)) menu.removeAttribute("open");
      });
    });
    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      document.querySelectorAll("details.menu[open]").forEach(function (menu) {
        menu.removeAttribute("open");
        var summary = menu.querySelector("summary");
        if (summary) summary.focus();
      });
    });
  });

  document.addEventListener("htmx:afterSwap", function (event) {
    syncClaims(event.target);
    bindAutoSubmit(event.target);
  });
})();
