// CodeGuard progressive enhancements. Every feature also works without JS
// except the "add rule" helper (the form always provides one blank row), the
// account menu (its pages are also linked from Settings) and chart tooltips
// (every chart also has a table and a text description).
(function () {
  "use strict";

  // Confirmation before destructive actions: <form data-confirm="message">
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  // Loading feedback: <form data-loading> disables its submit button.
  document.querySelectorAll("form[data-loading]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var button = form.querySelector("button[type=submit]");
      if (button) {
        button.classList.add("is-loading");
        button.setAttribute("aria-busy", "true");
        window.setTimeout(function () { button.disabled = true; }, 0);
      }
    });
  });

  // Print buttons (report documents).
  document.querySelectorAll("[data-print]").forEach(function (button) {
    button.hidden = false;
    button.addEventListener("click", function () { window.print(); });
  });

  // Horizontally scrolling regions (wide tables, diagrams, charts) must be
  // reachable and named for keyboard and screen-reader users (WCAG 2.1.1).
  // Only regions that actually overflow get a tab stop.
  var SCROLLERS = ".table-responsive, .cg-pipeline-scroll, .cg-chart-scroll";
  function labelScrollRegions() {
    document.querySelectorAll(SCROLLERS).forEach(function (region) {
      if (region.scrollWidth > region.clientWidth) {
        var section = region.closest("section");
        var heading = section && section.querySelector("h2, h3");
        region.setAttribute("tabindex", "0");
        region.setAttribute("role", "region");
        region.setAttribute("aria-label", (heading ? heading.textContent.trim() + " " : "") + "(scrolls horizontally)");
      } else if (region.getAttribute("tabindex") === "0") {
        region.removeAttribute("tabindex");
        region.removeAttribute("role");
        region.removeAttribute("aria-label");
      }
    });
  }
  labelScrollRegions();
  window.addEventListener("resize", labelScrollRegions);
  // Content can widen after load (e.g. when the web fonts arrive), so
  // re-check whenever a region or its content changes size.
  if (window.ResizeObserver) {
    var observer = new ResizeObserver(labelScrollRegions);
    document.querySelectorAll(SCROLLERS).forEach(function (region) {
      observer.observe(region);
      if (region.firstElementChild) {
        observer.observe(region.firstElementChild);
      }
    });
  }

  // Server-drawn charts are Matplotlib PNGs. Read the current theme's colour
  // tokens and ask for the chart in those colours (?palette=, the order of
  // simulation/charts.py PALETTE_TOKENS). data-chart-palette holds the
  // palette the current src was drawn with, so unchanged charts are not
  // fetched again. Inline SVG charts use the tokens directly.
  var CHART_TOKENS = ["surface", "text", "text-muted", "border", "border-strong",
    "sev-low", "sev-med", "sev-high", "sev-crit"];
  function renderCharts() {
    var style = getComputedStyle(document.documentElement);
    var palette = CHART_TOKENS.map(function (token) {
      return style.getPropertyValue("--" + token).trim().replace("#", "").toUpperCase();
    }).join(",");
    document.querySelectorAll("img[data-chart-palette]").forEach(function (img) {
      if (img.getAttribute("data-chart-palette") === palette) { return; }
      var url = new URL(img.getAttribute("src"), window.location.href);
      url.searchParams.set("palette", palette);
      img.setAttribute("src", url.pathname + url.search);
      img.setAttribute("data-chart-palette", palette);
    });
  }
  renderCharts();

  // Theme: the pre-paint script in <head> (core/theme.py) already applied the
  // account preference, the saved choice or the OS setting. The toggle
  // switches between light and dark. Signed-in users' choice is saved to
  // their account (the toggle sits in a form); visitors' in localStorage.
  // Until there is an explicit choice, the page follows OS changes live.
  var THEME_KEY = "codeguard-theme";
  var root = document.documentElement;
  function currentTheme() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }
  function syncToggles() {
    var dark = currentTheme() === "dark";
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      // Show where the button goes: a sun in dark mode, a moon in light mode.
      button.querySelector(".bi").className = "bi " + (dark ? "bi-sun" : "bi-moon");
      button.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
      button.hidden = false;
    });
  }
  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-bs-theme", theme);
    syncToggles();
    renderCharts();
  }
  syncToggles();
  document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
    var form = button.closest("form[data-theme-form]");
    if (form) {
      form.addEventListener("submit", function (event) {
        var next = currentTheme() === "dark" ? "light" : "dark";
        form.querySelector("input[name=mode]").value = next;
        if (!window.fetch) { return; } // plain form post; the server redirects back
        event.preventDefault();
        root.setAttribute("data-theme-pref", next);
        applyTheme(next);
        window.fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { "X-Requested-With": "fetch" },
          credentials: "same-origin"
        }).catch(function () { /* offline: the theme still applies to this page */ });
      });
    } else {
      button.addEventListener("click", function () {
        var next = currentTheme() === "dark" ? "light" : "dark";
        try { window.localStorage.setItem(THEME_KEY, next); } catch (e) { /* storage blocked: theme lasts for this page */ }
        applyTheme(next);
      });
    }
  });
  if (window.matchMedia) {
    var osDark = window.matchMedia("(prefers-color-scheme: dark)");
    var followOs = function (event) {
      var pref = root.getAttribute("data-theme-pref");
      if (pref === "light" || pref === "dark") { return; }
      if (pref !== "system") {
        var saved = null;
        try { saved = window.localStorage.getItem(THEME_KEY); } catch (e) { /* storage blocked */ }
        if (saved === "light" || saved === "dark") { return; }
      }
      applyTheme(event.matches ? "dark" : "light");
    };
    if (osDark.addEventListener) { osDark.addEventListener("change", followOs); }
  }

  // Chart tooltips: any element with data-tip="Title|detail" shows a tooltip
  // on hover and on keyboard focus. Text is inserted with textContent.
  var tip = document.getElementById("cg-tooltip");
  function showTip(target, x, y) {
    if (!tip) { return; }
    var parts = (target.getAttribute("data-tip") || "").split("|");
    tip.textContent = "";
    var strong = document.createElement("strong");
    strong.textContent = parts[0];
    tip.appendChild(strong);
    if (parts[1]) { tip.appendChild(document.createTextNode(parts[1])); }
    tip.hidden = false;
    var box = tip.getBoundingClientRect();
    var left = Math.min(Math.max(8, x + 14), window.innerWidth - box.width - 8);
    var top = y - box.height - 12;
    if (top < 8) { top = y + 18; }
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }
  function hideTip() { if (tip) { tip.hidden = true; } }
  document.querySelectorAll("[data-tip]").forEach(function (el) {
    // The native <title> stays for screen readers; hide it from hover while JS draws the tooltip.
    var title = el.querySelector("title");
    if (title) { el.setAttribute("role", "img"); el.setAttribute("aria-label", title.textContent); title.remove(); }
    el.addEventListener("pointermove", function (event) { showTip(el, event.clientX, event.clientY); });
    el.addEventListener("pointerleave", hideTip);
    el.addEventListener("focus", function () {
      var r = el.getBoundingClientRect();
      showTip(el, r.left + r.width / 2, r.top);
    });
    el.addEventListener("blur", hideTip);
  });
  document.addEventListener("keydown", function (event) { if (event.key === "Escape") { hideTip(); } });
  window.addEventListener("scroll", hideTip, { passive: true });

  // Simulation configuration stepper. Without JS every step is visible and
  // the form submits from anywhere; with JS one step shows at a time.
  var stepper = document.querySelector("form[data-stepper]");
  if (stepper) {
    var panels = Array.prototype.slice.call(stepper.querySelectorAll("[data-step]"));
    var tabs = Array.prototype.slice.call(document.querySelectorAll("[data-step-tab]"));
    var back = stepper.querySelector("[data-step-back]");
    var next = stepper.querySelector("[data-step-next]");
    var submit = stepper.querySelector("[data-step-submit]");
    var current = 0;
    function refreshReview() {
      stepper.querySelectorAll("[data-review-of]").forEach(function (cell) {
        var input = document.getElementById(cell.getAttribute("data-review-of"));
        if (input) { cell.textContent = input.value || "—"; }
      });
      var count = stepper.querySelectorAll("input[name=controls]:checked").length;
      var target = stepper.querySelector("[data-review-controls]");
      if (target) { target.textContent = count === 0 ? "None (inherent run)" : String(count); }
    }
    function show(index, focus) {
      current = Math.max(0, Math.min(index, panels.length - 1));
      panels.forEach(function (panel, i) { panel.hidden = i !== current; });
      tabs.forEach(function (tab, i) {
        if (i === current) { tab.setAttribute("aria-current", "step"); } else { tab.removeAttribute("aria-current"); }
        tab.classList.toggle("is-done", i < current);
      });
      back.hidden = current === 0;
      next.hidden = current === panels.length - 1;
      submit.hidden = current !== panels.length - 1;
      if (current === panels.length - 1) { refreshReview(); }
      if (focus) {
        var heading = panels[current].querySelector("h2");
        if (heading) { heading.setAttribute("tabindex", "-1"); heading.focus(); }
      }
    }
    back.addEventListener("click", function () { show(current - 1, true); });
    next.addEventListener("click", function () { show(current + 1, true); });
    // After a failed submit, open the first step that has an error.
    var firstError = panels.findIndex(function (panel) {
      return panel.querySelector("[aria-invalid=true], .invalid-feedback");
    });
    show(firstError >= 0 ? firstError : 0, false);
  }

  // Control selection helpers on the simulation form.
  function setControls(predicate) {
    document.querySelectorAll("input[name=controls]").forEach(function (box) {
      box.checked = predicate(box);
    });
  }
  var selectApplicable = document.getElementById("select-applicable");
  if (selectApplicable) {
    selectApplicable.addEventListener("click", function () {
      setControls(function (box) { return box.dataset.applicable === "1"; });
    });
  }
  var selectAll = document.getElementById("select-all-controls");
  if (selectAll) {
    selectAll.addEventListener("click", function () { setControls(function () { return true; }); });
  }
  var clearControls = document.getElementById("clear-controls");
  if (clearControls) {
    clearControls.addEventListener("click", function () { setControls(function () { return false; }); });
  }

  // Dynamic propagation-rule formset rows.
  var addRule = document.getElementById("add-rule");
  if (addRule) {
    addRule.addEventListener("click", function () {
      var total = document.getElementById("id_rules-TOTAL_FORMS");
      var max = document.getElementById("id_rules-MAX_NUM_FORMS");
      var index = parseInt(total.value, 10);
      if (max && index >= parseInt(max.value, 10)) {
        addRule.disabled = true;
        return;
      }
      var template = document.getElementById("rule-template");
      var html = template.innerHTML.replace(/__prefix__/g, String(index));
      var container = document.getElementById("rule-rows");
      container.insertAdjacentHTML("beforeend", html);
      total.value = String(index + 1);
      var first = container.lastElementChild.querySelector("select");
      if (first) { first.focus(); }
    });
  }
})();
