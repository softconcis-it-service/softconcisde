/* Softconcis Consent Manager – lightweight, GDPR-style cookie consent
   Data source: site's original consent configuration (groups, services, providers). */
(function () {
  "use strict";
  var C = window.SCC_CONFIG;
  if (!C) return;
  var T = C.texts;
  var KEY = "scc-consent-v1";
  var state = null;
  var activated = {};

  /* ---------- storage ---------- */
  function read() {
    try { return JSON.parse(localStorage.getItem(KEY)); } catch (e) { return null; }
  }
  function persist() {
    localStorage.setItem(KEY, JSON.stringify(state));
  }
  function hasChoice() { return !!state; }
  function consented(sid) {
    var g = groupOf(sid);
    if (g && g.id === "essential") return true;
    return !!(state && state.services && state.services[sid]);
  }
  function groupOf(sid) {
    for (var i = 0; i < C.groups.length; i++) {
      if (C.groups[i].serviceIds.indexOf(sid) !== -1) return C.groups[i];
    }
    return null;
  }

  /* ---------- unblocking ---------- */
  function activate(sid) {
    if (activated[sid]) return;
    var svc = C.services[sid];
    if (!svc) return;
    activated[sid] = true;
    (svc.blockerIds || []).forEach(function (bid) {
      var tpls = document.querySelectorAll(
        'script[type="text/template"][data-consent-mgr-script-blocker-id="' + bid + '"]'
      );
      tpls.forEach(function (t) {
        var s = document.createElement("script");
        var src = t.getAttribute("data-consent-mgr-script-blocker-src");
        if (src) s.src = src.indexOf("//") === 0 ? "https:" + src : src;
        else s.text = t.textContent;
        t.parentNode.replaceChild(s, t);
      });
    });
    if (svc.fallbackSrc && svc.srcMarker &&
        !document.querySelector('script[src*="' + svc.srcMarker + '"]')) {
      var s2 = document.createElement("script");
      s2.src = svc.fallbackSrc;
      document.head.appendChild(s2);
    }
    if (svc.execCode) {
      var s3 = document.createElement("script");
      s3.text = svc.execCode;
      document.head.appendChild(s3);
    }
    document.querySelectorAll('.scc-blocked[data-scc-service="' + sid + '"]').forEach(function (ph) {
      ph.parentNode.removeChild(ph);
    });
  }
  function applyConsents() {
    if (!state) return;
    Object.keys(state.services || {}).forEach(function (sid) {
      if (state.services[sid]) activate(sid);
    });
  }

  /* ---------- helpers ---------- */
  function el(tag, cls, htmlContent) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (htmlContent != null) e.innerHTML = htmlContent;
    return e;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* ---------- blocked-content placeholders ---------- */
  function setupPlaceholders() {
    Object.keys(C.embedSelectors || {}).forEach(function (sid) {
      if (consented(sid)) return;
      var svc = C.services[sid];
      var prov = C.providers[svc ? svc.providerId : ""] || { name: sid };
      document.querySelectorAll(C.embedSelectors[sid]).forEach(function (target) {
        if (target.__sccDone) return;
        target.__sccDone = true;
        var ph = el("div", "scc-blocked");
        ph.setAttribute("data-scc-service", sid);
        var info = T.blockedInfo.replace("{provider}", esc(prov.name));
        var details =
          '<div class="scc-blocked-details" hidden>' +
          '<p>' + esc(prov.description) + "</p>" +
          '<p><strong>' + esc(T.providerName) + ":</strong> " + esc(prov.name) +
          (prov.address ? " · " + esc(prov.address) : "") + "</p>" +
          (prov.privacyUrl
            ? '<p><a href="' + esc(prov.privacyUrl) + '" target="_blank" rel="noopener">' +
              esc(T.privacyLink) + "</a></p>"
            : "") +
          '<p class="scc-hint">' + esc(T.acceptHint) + "</p>" +
          "</div>";
        ph.innerHTML =
          '<p class="scc-blocked-info">' + info + "</p>" + details +
          '<div class="scc-blocked-actions">' +
          '<button type="button" class="scc-btn scc-btn-primary" data-scc-unblock>' +
          esc(T.unblockButton) + "</button>" +
          '<button type="button" class="scc-btn scc-btn-link" data-scc-moreinfo>' +
          esc(T.moreInfo) + "</button></div>";
        ph.querySelector("[data-scc-unblock]").addEventListener("click", function () {
          if (!state) state = { groups: {}, services: {}, ts: Date.now() };
          state.services[sid] = true;
          var g = groupOf(sid);
          if (g) state.groups[g.id] = true;
          persist();
          activate(sid);
        });
        ph.querySelector("[data-scc-moreinfo]").addEventListener("click", function () {
          var d = ph.querySelector(".scc-blocked-details");
          d.hidden = !d.hidden;
        });
        target.parentNode.insertBefore(ph, target);
      });
    });
  }

  /* ---------- dialog ---------- */
  var root, backdrop, dialog;
  function legalText() {
    return [
      T.legalInformationDescriptionTechnology,
      T.legalInformationDescriptionPersonalData,
      T.legalInformationDescriptionNonEuDataTransfer,
      T.legalInformationDescriptionConfirmAge,
      T.legalInformationDescriptionRevoke,
      T.legalInformationDescriptionMoreInformation,
      T.legalInformationDescriptionNoObligation,
    ].filter(Boolean).map(function (p) { return "<p>" + p + "</p>"; }).join("");
  }

  function currentSelection() {
    var sel = {};
    C.groups.forEach(function (g) {
      sel[g.id] = g.id === "essential" ? true
        : state && state.groups ? !!state.groups[g.id] : false;
    });
    return sel;
  }

  function serviceInfoHTML(svc) {
    var prov = C.providers[svc.providerId] || {};
    var rows = "";
    rows += '<tr><th>' + esc(T.serviceDetailsTableName) + "</th><td>" + esc(svc.name) + "</td></tr>";
    if (svc.description)
      rows += '<tr><th>' + esc(T.serviceDetailsTableDescription) + "</th><td>" + esc(svc.description) + "</td></tr>";
    if (prov.name)
      rows += '<tr><th>' + esc(T.providerName) + "</th><td>" + esc(prov.name) +
        (prov.address ? "<br>" + esc(prov.address) : "") + "</td></tr>";
    if (prov.privacyUrl)
      rows += '<tr><th>' + esc(T.providerPrivacyUrl) + '</th><td><a href="' + esc(prov.privacyUrl) +
        '" target="_blank" rel="noopener">' + esc(prov.privacyUrl) + "</a></td></tr>";
    if (prov.cookieUrl)
      rows += '<tr><th>' + esc(T.providerCookieUrl) + '</th><td><a href="' + esc(prov.cookieUrl) +
        '" target="_blank" rel="noopener">' + esc(prov.cookieUrl) + "</a></td></tr>";
    if (svc.hosts && svc.hosts.length)
      rows += '<tr><th>' + esc(T.serviceDetailsTableHosts) + "</th><td>" + esc(svc.hosts.join(", ")) + "</td></tr>";
    var cookieRows = "";
    (svc.cookies || []).forEach(function (c) {
      cookieRows += "<tr><td>" + esc(c.name) + "</td><td>" + esc(c.lifetime) + "</td><td>" +
        esc(c.description) + "</td></tr>";
    });
    var cookieTable = cookieRows
      ? '<table class="scc-cookie-table"><thead><tr><th>' + esc(T.serviceDetailsTableCookies) +
        "</th><th>" + esc(T.serviceDetailsTableCookieLifetime) + "</th><th>" +
        esc(T.serviceDetailsTableDescription) + "</th></tr></thead><tbody>" + cookieRows + "</tbody></table>"
      : "";
    return '<table class="scc-info-table"><tbody>' + rows + "</tbody></table>" + cookieTable;
  }

  function render(view) {
    if (!root) {
      root = el("div", "scc-root");
      backdrop = el("div", "scc-backdrop");
      dialog = el("div", "scc-dialog");
      dialog.setAttribute("role", "dialog");
      dialog.setAttribute("aria-modal", "true");
      dialog.setAttribute("aria-label", (T && (T.detailsHeadline || T.entranceHeadline)) || "Cookie-Einstellungen");
      root.appendChild(backdrop);
      root.appendChild(dialog);
      document.body.appendChild(root);
    }
    root.style.display = "";
    dialog.innerHTML = "";
    if (view === "entrance") renderEntrance();
    else renderDetails();
    // in den sichtbaren Zustand überblenden: erst den versteckten Ausgangs-
    // zustand per Reflow committen, dann die Klasse setzen -> CSS-Transition
    // läuft (funktioniert anders als requestAnimationFrame auch im Hintergrund-Tab)
    void root.offsetWidth;
    root.classList.add("scc-open");
  }

  function hideDialog() {
    // Klasse entfernen -> Backdrop/Dialog blenden per CSS aus (das Overlay
    // bleibt im DOM, ist per visibility:hidden aber inaktiv)
    if (root) root.classList.remove("scc-open");
  }

  function groupCheckboxes(sel, interactive) {
    var wrap = el("div", "scc-groups");
    C.groups.forEach(function (g) {
      var id = "scc-g-" + g.id;
      var item = el("label", "scc-group");
      item.setAttribute("for", id);
      item.innerHTML =
        '<input type="checkbox" id="' + id + '" data-scc-group="' + g.id + '"' +
        (sel[g.id] ? " checked" : "") + (g.id === "essential" ? " disabled" : "") + ">" +
        "<span>" + esc(g.name) + "</span>";
      wrap.appendChild(item);
    });
    return wrap;
  }

  function collectSelection(container) {
    var sel = { essential: true };
    container.querySelectorAll("[data-scc-group]").forEach(function (cb) {
      sel[cb.getAttribute("data-scc-group")] = cb.checked || cb.disabled;
    });
    return sel;
  }

  function saveSelection(sel) {
    var prev = state && state.services ? state.services : {};
    var services = {};
    var revokedActive = false;
    C.groups.forEach(function (g) {
      g.serviceIds.forEach(function (sid) {
        var on = g.id === "essential" ? true : !!sel[g.id];
        services[sid] = on;
        if (!on && activated[sid]) revokedActive = true;
        if (!on && prev[sid] && activated[sid]) revokedActive = true;
      });
    });
    state = { groups: sel, services: services, ts: Date.now() };
    persist();
    hideDialog();
    showWidget();
    if (revokedActive) { location.reload(); return; }
    applyConsents();
    setupPlaceholders();
  }

  function acceptAll() {
    var sel = {};
    C.groups.forEach(function (g) { sel[g.id] = true; });
    saveSelection(sel);
  }
  function essentialOnly() {
    var sel = {};
    C.groups.forEach(function (g) { sel[g.id] = g.id === "essential"; });
    saveSelection(sel);
  }

  function renderEntrance() {
    var sel = currentSelection();
    dialog.className = "scc-dialog scc-entrance";
    var head = el("div", "scc-head",
      "<h2>" + esc(T.entranceHeadline) + "</h2>" +
      '<button type="button" class="scc-close" aria-label="' + esc(T.a11yDialogCloseButton) + '">&times;</button>');
    var body = el("div", "scc-body", '<div class="scc-legal">' + legalText() + "</div>");
    var groupsBox = groupCheckboxes(sel, true);
    var actions = el("div", "scc-actions");
    var btnAll = el("button", "scc-btn scc-btn-primary", esc(T.entranceAcceptAllButton));
    btnAll.type = "button";
    var btnSave = el("button", "scc-btn scc-btn-secondary", esc(T.entranceSaveConsentButton));
    btnSave.type = "button";
    var btnEss = el("button", "scc-btn scc-btn-secondary", esc(T.entranceAcceptOnlyEssential));
    btnEss.type = "button";
    actions.appendChild(btnAll); actions.appendChild(btnSave); actions.appendChild(btnEss);
    var links = el("div", "scc-links",
      '<a href="#" data-scc-open-details>' + esc(T.entrancePreferencesButton) + "</a>" +
      '<a href="' + esc(C.privacyUrl) + '">' + esc(T.privacyLink) + "</a>" +
      '<a href="' + esc(C.imprintUrl) + '">' + esc(T.imprintLink) + "</a>");
    dialog.appendChild(head); dialog.appendChild(body);
    dialog.appendChild(groupsBox); dialog.appendChild(actions); dialog.appendChild(links);

    btnAll.addEventListener("click", acceptAll);
    btnEss.addEventListener("click", essentialOnly);
    btnSave.addEventListener("click", function () { saveSelection(collectSelection(groupsBox)); });
    head.querySelector(".scc-close").addEventListener("click", essentialOnly);
    links.querySelector("[data-scc-open-details]").addEventListener("click", function (e) {
      e.preventDefault(); render("details");
    });
    bindActionLinks(dialog);
  }

  function renderDetails() {
    var sel = currentSelection();
    dialog.className = "scc-dialog scc-details";
    var head = el("div", "scc-head",
      "<h2>" + esc(T.detailsHeadline) + "</h2>" +
      '<button type="button" class="scc-close" aria-label="' + esc(T.a11yDialogCloseButton) + '">&times;</button>');
    var body = el("div", "scc-body");
    body.appendChild(el("p", "scc-desc", T.detailsDescription));
    C.groups.forEach(function (g) {
      var sec = el("section", "scc-group-section");
      var swId = "scc-sw-" + g.id;
      sec.innerHTML =
        '<div class="scc-group-head">' +
        '<label class="scc-switch"><input type="checkbox" id="' + swId + '" data-scc-group="' + g.id + '"' +
        (sel[g.id] ? " checked" : "") + (g.id === "essential" ? " disabled" : "") +
        '><span class="scc-slider"></span></label>' +
        "<div><h3>" + esc(g.name) + "</h3><p>" + esc(g.description) + "</p></div></div>";
      var list = el("div", "scc-service-list");
      g.serviceIds.forEach(function (sid) {
        var svc = C.services[sid];
        if (!svc) return;
        var item = el("div", "scc-service");
        item.innerHTML =
          '<div class="scc-service-row"><span class="scc-service-name">' + esc(svc.name) + "</span>" +
          '<a href="#" class="scc-toggle-info">' + esc(T.detailsShowMoreInformationLink) + "</a></div>" +
          '<div class="scc-service-info" hidden>' + serviceInfoHTML(svc) + "</div>";
        item.querySelector(".scc-toggle-info").addEventListener("click", function (e) {
          e.preventDefault();
          var info = item.querySelector(".scc-service-info");
          info.hidden = !info.hidden;
          e.target.textContent = info.hidden ? T.detailsShowMoreInformationLink : T.detailsHideMoreInformationLink;
        });
        list.appendChild(item);
      });
      sec.appendChild(list);
      body.appendChild(sec);
    });
    var actions = el("div", "scc-actions");
    var btnAll = el("button", "scc-btn scc-btn-primary", esc(T.detailsAcceptAllButton));
    btnAll.type = "button";
    var btnSave = el("button", "scc-btn scc-btn-secondary", esc(T.detailsSaveConsentButton));
    btnSave.type = "button";
    var btnEss = el("button", "scc-btn scc-btn-secondary", esc(T.detailsAcceptOnlyEssential));
    btnEss.type = "button";
    actions.appendChild(btnAll); actions.appendChild(btnSave); actions.appendChild(btnEss);
    var links = el("div", "scc-links",
      '<a href="#" data-scc-back>' + esc(T.detailsBackLink) + "</a>" +
      '<a href="' + esc(C.privacyUrl) + '">' + esc(T.privacyLink) + "</a>" +
      '<a href="' + esc(C.imprintUrl) + '">' + esc(T.imprintLink) + "</a>");
    dialog.appendChild(head); dialog.appendChild(body);
    dialog.appendChild(actions); dialog.appendChild(links);

    btnAll.addEventListener("click", acceptAll);
    btnEss.addEventListener("click", essentialOnly);
    btnSave.addEventListener("click", function () { saveSelection(collectSelection(body)); });
    head.querySelector(".scc-close").addEventListener("click", function () {
      if (hasChoice()) hideDialog(); else essentialOnly();
    });
    links.querySelector("[data-scc-back]").addEventListener("click", function (e) {
      e.preventDefault();
      if (hasChoice()) hideDialog(); else render("entrance");
    });
    bindActionLinks(dialog);
  }

  function bindActionLinks(scope) {
    scope.querySelectorAll('[data-scc-action="open"]').forEach(function (a) {
      a.addEventListener("click", function (e) { e.preventDefault(); render("details"); });
    });
  }

  /* ---------- widget button ---------- */
  var widget;
  function showWidget() {
    if (widget) { widget.style.display = ""; widget.classList.add("scc-in"); return; }
    widget = el("button", "scc-widget");
    widget.type = "button";
    widget.setAttribute("aria-label", T.a11yWidgetButton);
    widget.innerHTML =
      '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M12 2a10 10 0 1 0 10 10 1 1 0 0 0-1-1h-3.1a1.9 1.9 0 0 1-1.9-1.9V8.9A1.9 1.9 0 0 1 17.9 7H21a1 1 0 0 0 .95-1.32A10 10 0 0 0 12 2zm-4.5 8A1.5 1.5 0 1 1 6 11.5 1.5 1.5 0 0 1 7.5 10zm2 6A1.5 1.5 0 1 1 8 17.5 1.5 1.5 0 0 1 9.5 16zm5 .5A1.5 1.5 0 1 1 13 15a1.5 1.5 0 0 1 1.5 1.5zM12 6.5A1.5 1.5 0 1 1 10.5 8 1.5 1.5 0 0 1 12 6.5z"/></svg>';
    widget.addEventListener("click", function () { render("details"); });
    document.body.appendChild(widget);
    void widget.offsetWidth;
    widget.classList.add("scc-in");
  }

  /* ---------- init ---------- */
  function init() {
    state = read();
    applyConsents();
    setupPlaceholders();
    if (!hasChoice()) render("entrance");
    else showWidget();
    // reopen dialog via legacy consentmgr links (e.g. in the privacy policy)
    document.querySelectorAll("[data-consent-mgr-actions], a[href*='#consent-mgr']").forEach(function (a) {
      a.addEventListener("click", function (e) { e.preventDefault(); render("details"); });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
