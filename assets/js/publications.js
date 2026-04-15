/* Publications renderer — reads window.PUBLICATIONS (from publications-data.js)
 * and renders filterable year-grouped list into #pub-list. */
(function () {
  "use strict";

  var ME_RE = /^F\.?\s*Silvestri$/i;

  function byId(id) { return document.getElementById(id); }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  var TYPE_LABELS = {
    a_star_conf: "A* Conf.",
    q1_journal: "Q1 Journal",
    other: "Other",
    preprint: "Preprint"
  };

  function renderAuthors(authors) {
    return authors
      .map(function (a) {
        var safe = escapeHtml(a);
        return ME_RE.test(a) ? '<span class="me">' + safe + "</span>" : safe;
      })
      .join(", ");
  }

  function renderVenue(pub) {
    var venue = pub.venue || "";
    if (!venue) return String(pub.year || "");
    return escapeHtml(venue) + (pub.year ? " · " + pub.year : "");
  }

  function renderItem(pub) {
    var titleHtml = pub.url
      ? '<a href="' + escapeHtml(pub.url) + '" target="_blank" rel="noopener">' +
        escapeHtml(pub.title) + "</a>"
      : escapeHtml(pub.title);
    return (
      '<article class="pub-item">' +
        '<span class="pub-badge type-' + pub.type + '">' +
          escapeHtml(TYPE_LABELS[pub.type] || pub.type) +
        "</span>" +
        '<div class="pub-body">' +
          '<h3 class="pub-title">' + titleHtml + "</h3>" +
          '<p class="pub-authors">' + renderAuthors(pub.authors || []) + "</p>" +
          '<p class="pub-venue">' + renderVenue(pub) + "</p>" +
        "</div>" +
      "</article>"
    );
  }

  function groupByYear(pubs) {
    var groups = {};
    pubs.forEach(function (p) {
      var y = p.year || 0;
      if (!groups[y]) groups[y] = [];
      groups[y].push(p);
    });
    return Object.keys(groups)
      .map(Number)
      .sort(function (a, b) { return b - a; })
      .map(function (y) { return { year: y, pubs: groups[y] }; });
  }

  function render(filter) {
    var data = window.PUBLICATIONS;
    var list = byId("pub-list");
    if (!list) return;
    if (!data || !data.publications) {
      list.innerHTML = '<p class="pub-empty">No publication data found. Run scripts/fetch_publications.py.</p>';
      return;
    }
    var pubs = data.publications;
    if (filter && filter !== "all") {
      pubs = pubs.filter(function (p) { return p.type === filter; });
    }
    if (pubs.length === 0) {
      list.innerHTML = '<p class="pub-empty">No publications in this category.</p>';
      return;
    }
    var html = groupByYear(pubs)
      .map(function (g) {
        return (
          '<div class="pub-year-block">' +
            '<div class="pub-year">' + g.year + "</div>" +
            g.pubs.map(renderItem).join("") +
          "</div>"
        );
      })
      .join("");
    list.innerHTML = html;
  }

  function updateStats() {
    var data = window.PUBLICATIONS;
    if (!data) return;
    var totalEl = byId("stat-pubs");
    var astarEl = byId("stat-astar");
    var yearsEl = byId("stat-years");
    var updEl = byId("pub-last-updated");
    if (totalEl) totalEl.textContent = data.count || "—";
    if (astarEl && data.counts_by_type) {
      astarEl.textContent = data.counts_by_type.a_star_conf || 0;
    }
    if (yearsEl && data.years && data.years.length) {
      var span = data.years[0] - data.years[data.years.length - 1] + 1;
      yearsEl.textContent = span + "+";
    }
    if (updEl) updEl.textContent = data.last_updated || "—";
  }

  function initTabs() {
    var bar = byId("pub-filters");
    if (!bar) return;
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".pub-tab");
      if (!btn) return;
      var filter = btn.getAttribute("data-filter");
      bar.querySelectorAll(".pub-tab").forEach(function (b) {
        b.classList.toggle("is-active", b === btn);
      });
      render(filter);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    updateStats();
    initTabs();
    render("all");
  });
})();
