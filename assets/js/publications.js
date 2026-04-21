/* Publications renderer — reads window.PUBLICATIONS (from publications-data.js)
 * and renders a year-grouped list with two filter dimensions:
 *   - TYPE (A*, Q1, Other, Workshop, Preprint) in #pub-filters
 *   - TOPIC (IR, RecSys, LLM & Agentic AI, …) in #topic-filters
 * The two filters are ANDed. Clicking a topic chip on a paper activates
 * that topic filter. */
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

  var TYPE_FALLBACK = {
    a_star_conf:   "A/A* Conference",
    q1_journal:    "Q1 Journal",
    other_conf:    "Other Conference",
    other_journal: "Other Journal",
    workshop:      "Workshop",
    preprint:      "Preprint"
  };

  var FILTER_TYPES = {
    a_star_conf:   ["a_star_conf"],
    q1_journal:    ["q1_journal"],
    other:         ["other_conf", "other_journal"],
    workshop:      ["workshop"],
    preprint:      ["preprint"]
  };

  // "Selected" is a hybrid high-impact filter: a paper qualifies iff it's
  // in a top-tier venue (A/A* conf or Q1 journal) AND either has ≥ N
  // Scholar citations OR is recent enough that citations haven't had
  // time to accumulate (last SELECTED_RECENT_YEARS calendar years).
  var SELECTED_CITE_THRESHOLD = 20;
  var SELECTED_RECENT_YEARS = 2;

  // Filter state. `showOlder` toggles the "> RECENT_YEARS old" section.
  var state = { type: "selected", topic: "all", showOlder: false };
  // Rolling window: always show the most-recent N years (not by calendar
  // year — by the most-recent year present in the data, so the window
  // stays a fixed 5 years wide even as time passes).
  var RECENT_YEARS = 5;
  // Map from topic slug -> display name, populated at init from topics_meta.
  var TOPIC_NAMES = {};

  function renderAuthors(authors) {
    return authors
      .map(function (a) {
        var safe = escapeHtml(a);
        return ME_RE.test(a) ? '<span class="me">' + safe + "</span>" : safe;
      })
      .join(", ");
  }

  function renderVenue(pub) {
    var parts = [];
    if (pub.venue) parts.push(escapeHtml(pub.venue));
    if (pub.year) parts.push(String(pub.year));
    if (pub.citations && pub.citations > 0) {
      var q = encodeURIComponent(pub.title || "");
      parts.push(
        '<a class="pub-cites" href="https://scholar.google.com/scholar?q=' + q +
        '" target="_blank" rel="noopener" title="Citations from Google Scholar">Cited by ' +
        pub.citations + '</a>'
      );
    }
    return parts.join(" · ");
  }

  function renderChips(topics) {
    if (!topics || !topics.length) return "";
    return (
      '<div class="pub-chips">' +
      topics.map(function (slug) {
        var name = TOPIC_NAMES[slug] || slug;
        return (
          '<button type="button" class="pub-chip" data-topic="' + escapeHtml(slug) +
          '" title="Filter by ' + escapeHtml(name) + '">' +
          escapeHtml(name) +
          "</button>"
        );
      }).join("") +
      "</div>"
    );
  }

  function renderItem(pub) {
    var titleHtml = pub.url
      ? '<a href="' + escapeHtml(pub.url) + '" target="_blank" rel="noopener">' +
        escapeHtml(pub.title) + "</a>"
      : escapeHtml(pub.title);
    var badgeText = pub.venue_short || TYPE_FALLBACK[pub.type] || pub.type;
    return (
      '<article class="pub-item">' +
        '<span class="pub-badge type-' + pub.type + '" title="' +
          escapeHtml(TYPE_FALLBACK[pub.type] || "") + '">' +
          escapeHtml(badgeText) +
        "</span>" +
        '<div class="pub-body">' +
          '<h3 class="pub-title">' + titleHtml + "</h3>" +
          '<p class="pub-authors">' + renderAuthors(pub.authors || []) + "</p>" +
          '<p class="pub-venue">' + renderVenue(pub) + "</p>" +
          renderChips(pub.topics) +
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

  function maxYear(data) {
    return (data.years && data.years.length) ? data.years[0] : 0;
  }

  function isSelected(pub, max) {
    // Hybrid high-impact: top-tier venue AND (≥ threshold cites OR recent).
    if (pub.type !== "a_star_conf" && pub.type !== "q1_journal") return false;
    if ((pub.citations || 0) >= SELECTED_CITE_THRESHOLD) return true;
    if (pub.year && pub.year >= max - (SELECTED_RECENT_YEARS - 1)) return true;
    return false;
  }

  function matchesType(pub, typeFilter, max) {
    // "all" excludes preprints — they're only visible via the
    // dedicated Preprints tab. Everything else is a peer-reviewed
    // venue (A*/Q1/Other conf/Other journal/Workshop).
    if (typeFilter === "all") return pub.type !== "preprint";
    if (typeFilter === "selected") return isSelected(pub, max);
    var types = FILTER_TYPES[typeFilter] || [typeFilter];
    return types.indexOf(pub.type) !== -1;
  }

  function selectedPubs(data) {
    var max = maxYear(data);
    return (data.publications || []).filter(function (p) { return isSelected(p, max); });
  }

  // IEEE-style plain-text bibliography. Conference papers get
  // "in Proc. <venue>, <year>."; journal articles get "<venue>, <year>."
  // Authors use the IEEE "A, B, and C" convention (Oxford comma).
  function formatAuthorsIEEE(authors) {
    if (!authors || authors.length === 0) return "";
    if (authors.length === 1) return authors[0];
    if (authors.length === 2) return authors[0] + " and " + authors[1];
    return authors.slice(0, -1).join(", ") + ", and " + authors[authors.length - 1];
  }

  function toIEEE(pub, n) {
    var authors = formatAuthorsIEEE(pub.authors || []);
    var title = (pub.title || "").replace(/\.+$/, "");
    var venue = pub.venue_short || pub.venue || "";
    var year = pub.year || "";
    var venueText = pub.type === "q1_journal" ? venue : "in Proc. " + venue;
    return "[" + n + "] " + authors + ", “" + title + ",” " + venueText + ", " + year + ".";
  }

  function buildIEEEDocument(data) {
    var pubs = selectedPubs(data).slice().sort(function (a, b) {
      if (b.year !== a.year) return b.year - a.year;
      return (a.title || "").localeCompare(b.title || "");
    });
    var header = [
      "Publications — Fabrizio Silvestri",
      "Selected: high-impact papers — CORE A/A* conferences or Scimago Q1 (CS)",
      "journals with at least " + SELECTED_CITE_THRESHOLD + " Google Scholar citations,",
      "or published in the last " + SELECTED_RECENT_YEARS + " years.",
      "Source: https://dblp.org/pid/s/FabrizioSilvestri.html",
      "Generated: " + (data.last_updated || new Date().toISOString().slice(0, 10)),
      "Count: " + pubs.length,
      "",
      "References (IEEE style)",
      ""
    ].join("\n");
    var body = pubs.map(function (p, i) { return toIEEE(p, i + 1); }).join("\n");
    return header + body + "\n";
  }

  function downloadIEEE() {
    var data = window.PUBLICATIONS;
    if (!data) return;
    var text = buildIEEEDocument(data);
    var blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "silvestri-publications-ieee.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 0);
  }

  function matchesTopic(pub, topicFilter) {
    if (topicFilter === "all") return true;
    return (pub.topics || []).indexOf(topicFilter) !== -1;
  }

  function renderGroups(groups) {
    return groups
      .map(function (g) {
        return (
          '<div class="pub-year-block">' +
            '<div class="pub-year">' + g.year + "</div>" +
            g.pubs.map(renderItem).join("") +
          "</div>"
        );
      })
      .join("");
  }

  function render() {
    var data = window.PUBLICATIONS;
    var list = byId("pub-list");
    if (!list) return;
    if (!data || !data.publications) {
      list.innerHTML = '<p class="pub-empty">No publication data found. Run scripts/fetch_publications.py.</p>';
      return;
    }

    // Rolling 5-year window anchored on the most-recent year across the
    // full corpus (so the window doesn't shrink when a topic filter
    // happens to exclude the newest papers).
    var max = maxYear(data);
    var cutoff = max - (RECENT_YEARS - 1);

    var filtered = data.publications.filter(function (p) {
      return matchesType(p, state.type, max) && matchesTopic(p, state.topic);
    });

    var recent = filtered.filter(function (p) { return p.year >= cutoff; });
    var older  = filtered.filter(function (p) { return p.year <  cutoff; });

    var html = "";
    if (recent.length > 0) {
      html += renderGroups(groupByYear(recent));
    } else if (older.length === 0) {
      list.innerHTML = '<p class="pub-empty">No publications match the current filters.</p>';
      return;
    } else {
      html += '<p class="pub-empty">No publications in the last ' +
              RECENT_YEARS + ' years match the current filters.</p>';
    }

    if (older.length > 0) {
      if (state.showOlder) {
        html +=
          '<div class="pub-older-toggle-wrap">' +
            '<button type="button" class="pub-older-toggle" id="pub-older-toggle">' +
              'Hide older publications' +
            '</button>' +
          '</div>';
        html += renderGroups(groupByYear(older));
        html +=
          '<div class="pub-older-toggle-wrap">' +
            '<button type="button" class="pub-older-toggle" id="pub-older-toggle-bottom">' +
              'Hide older publications' +
            '</button>' +
          '</div>';
      } else {
        html +=
          '<div class="pub-older-toggle-wrap">' +
            '<button type="button" class="pub-older-toggle" id="pub-older-toggle">' +
              'Show ' + older.length + ' older publication' +
              (older.length === 1 ? '' : 's') +
              ' <span class="pub-older-years">(' +
                (cutoff - 1) + ' and earlier)</span>' +
            '</button>' +
          '</div>';
      }
    }

    list.innerHTML = html;
  }

  function handleOlderToggle(e) {
    var btn = e.target.closest("#pub-older-toggle, #pub-older-toggle-bottom");
    if (!btn) return;
    state.showOlder = !state.showOlder;
    render();
    // When expanding, scroll the newly-revealed section into view.
    if (state.showOlder) {
      var firstOld = document.querySelector(".pub-older-toggle-wrap + .pub-year-block");
      if (firstOld) firstOld.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function updateStats() {
    var data = window.PUBLICATIONS;
    if (!data) return;
    var totalEl = byId("stat-pubs");
    var astarEl = byId("stat-astar");
    var yearsEl = byId("stat-years");
    var updEl = byId("pub-last-updated");
    // Exclude preprints from the headline count so it matches the
    // default "All" filter view.
    if (totalEl && data.counts_by_type) {
      var peerReviewed = (data.count || 0) -
        (data.counts_by_type.preprint || 0);
      totalEl.textContent = peerReviewed || "—";
    }
    if (astarEl && data.counts_by_type) {
      astarEl.textContent = data.counts_by_type.a_star_conf || 0;
    }
    if (yearsEl && data.years && data.years.length) {
      var span = data.years[0] - data.years[data.years.length - 1] + 1;
      yearsEl.textContent = span + "+";
    }
    if (updEl) updEl.textContent = data.last_updated || "—";
  }

  function setTypeFilter(value) {
    state.type = value;
    state.showOlder = false;
    var bar = byId("pub-filters");
    if (bar) {
      bar.querySelectorAll(".pub-tab").forEach(function (b) {
        b.classList.toggle("is-active", b.getAttribute("data-filter") === value);
      });
    }
    render();
  }

  function setTopicFilter(value) {
    state.topic = value;
    state.showOlder = false;
    var bar = byId("topic-filters");
    if (bar) {
      bar.querySelectorAll(".pub-tab").forEach(function (b) {
        b.classList.toggle("is-active", b.getAttribute("data-filter") === value);
      });
    }
    render();
  }

  function initTypeTabs() {
    var bar = byId("pub-filters");
    if (!bar) return;
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".pub-tab");
      if (!btn) return;
      setTypeFilter(btn.getAttribute("data-filter"));
    });
  }

  function initTopicTabs() {
    var bar = byId("topic-filters");
    var data = window.PUBLICATIONS;
    if (!bar || !data || !data.topics_meta || !data.topics_meta.length) return;
    var counts = data.counts_by_topic || {};
    var html = '<button class="pub-tab is-active" data-filter="all">All topics</button>';
    data.topics_meta.forEach(function (t) {
      TOPIC_NAMES[t.slug] = t.name;
      var n = counts[t.slug] || 0;
      html +=
        '<button class="pub-tab" data-filter="' + t.slug + '">' +
        escapeHtml(t.name) +
        ' <span class="pub-tab-count">' + n + '</span>' +
        "</button>";
    });
    bar.innerHTML = html;
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".pub-tab");
      if (!btn) return;
      setTopicFilter(btn.getAttribute("data-filter"));
    });
  }

  function initChipClicks() {
    var list = byId("pub-list");
    if (!list) return;
    list.addEventListener("click", function (e) {
      // Older-publications toggle has priority over chip-click handling.
      if (e.target.closest("#pub-older-toggle, #pub-older-toggle-bottom")) {
        handleOlderToggle(e);
        return;
      }
      var chip = e.target.closest(".pub-chip");
      if (!chip) return;
      e.preventDefault();
      var slug = chip.getAttribute("data-topic");
      if (!slug) return;
      setTopicFilter(slug);
      // Scroll the publications section to the top so the user sees the effect.
      var pubs = document.getElementById("publications");
      if (pubs) pubs.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function initDownloadButton() {
    var btn = byId("pub-download-ieee");
    if (!btn) return;
    btn.addEventListener("click", downloadIEEE);
  }

  document.addEventListener("DOMContentLoaded", function () {
    updateStats();
    initTypeTabs();
    initTopicTabs();
    initChipClicks();
    initDownloadButton();
    render();
  });
})();
