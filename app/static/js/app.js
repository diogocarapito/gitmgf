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

  // First-visit notice (D38): a real modal (background inert, Esc does nothing) that accepts without a reload.
  function firstNotice() {
    var overlay = document.querySelector("[data-first-notice]");
    if (!overlay) return;
    var dialog = overlay.querySelector("dialog");
    var form = overlay.querySelector("form");
    if (dialog && dialog.showModal) {
      dialog.close();
      dialog.showModal();
      overlay.classList.add("is-modal");
      // Always open at the top, so small screens show the title first
      var title = dialog.querySelector("h2");
      if (title) title.focus({ preventScroll: true });
      dialog.scrollTop = 0;
      dialog.addEventListener("cancel", function (event) { event.preventDefault(); });
    }
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      fetch(form.action, { method: "POST", body: new FormData(form), headers: { "HX-Request": "true" }, credentials: "same-origin" })
        .then(function (response) {
          if (!response.ok) throw new Error(response.status);
          if (dialog && dialog.open) dialog.close();
          overlay.remove();
        })
        .catch(function () { form.submit(); });
    });
  }

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

  // Light/dark toggle (theme.js applies the saved choice early; without JS the button stays hidden).
  function currentTheme() {
    var set = document.documentElement.getAttribute("data-theme");
    if (set === "light" || set === "dark") return set;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function bindThemeToggle() {
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.hidden = false;
      btn.setAttribute("aria-pressed", currentTheme() === "dark" ? "true" : "false");
      btn.addEventListener("click", function () {
        var next = currentTheme() === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        try { localStorage.setItem("gitmgf-theme", next); } catch (e) { /* not persisted */ }
        document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
          b.setAttribute("aria-pressed", next === "dark" ? "true" : "false");
        });
      });
    });
  }

  // Report form: child sexual abuse material may be reported anonymously, so the email is cleared and disabled.
  function bindReportReason() {
    var wrap = document.querySelector("[data-report-reason]");
    var box = document.querySelector("[data-report-email]");
    if (!wrap || !box) return;
    var select = wrap.querySelector("select");
    var input = box.querySelector("input[type=email]");
    var note = box.querySelector("[data-csam-note]");
    if (!select || !input) return;
    function sync() {
      var anonymous = select.value === "csam";
      if (anonymous) input.value = "";
      input.disabled = anonymous;
      input.required = !anonymous;
      if (note) note.hidden = !anonymous;
    }
    select.addEventListener("change", sync);
    sync();
  }

  // Blog tabs: panels are consecutive sections without JS; here they become an ARIA tab list.
  function bindTabs(root) {
    root.querySelectorAll("[data-tabs]").forEach(function (box, b) {
      var panels = Array.prototype.slice.call(box.querySelectorAll(":scope > .ctabs__panel"));
      if (panels.length < 2) return;
      var list = document.createElement("div");
      list.className = "ctabs__list";
      list.setAttribute("role", "tablist");
      var buttons = panels.map(function (panel, i) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "ctabs__tab";
        btn.id = "tab-" + b + "-" + i;
        btn.setAttribute("role", "tab");
        btn.setAttribute("aria-controls", panel.id);
        btn.textContent = panel.getAttribute("data-tab-label");
        panel.setAttribute("role", "tabpanel");
        panel.setAttribute("aria-labelledby", btn.id);
        panel.setAttribute("tabindex", "0");
        list.appendChild(btn);
        return btn;
      });
      function select(index, focus) {
        buttons.forEach(function (btn, i) {
          var on = i === index;
          btn.setAttribute("aria-selected", on ? "true" : "false");
          btn.tabIndex = on ? 0 : -1;
          panels[i].hidden = !on;
        });
        if (focus) buttons[index].focus();
      }
      buttons.forEach(function (btn, i) {
        btn.addEventListener("click", function () { select(i, false); });
        btn.addEventListener("keydown", function (event) {
          var next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: buttons.length - 1 }[event.key];
          if (next === undefined) return;
          event.preventDefault();
          select((next + buttons.length) % buttons.length, true);
        });
      });
      box.insertBefore(list, box.firstChild);
      box.classList.add("ctabs--js");
      select(0, false);
    });
  }

  onReady(function () {
    firstNotice();
    bindThemeToggle();
    bindReportReason();
    bindTabs(document);
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
