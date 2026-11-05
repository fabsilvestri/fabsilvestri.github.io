/* Publications renderer — fetches data/publications.json with
 * cache: 'no-store' at page load (so counters and the publication list
 * are always live, no matter how stale the cached HTML is), then renders
 * a year-grouped list with two filter dimensions:
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

  // "Selected" = the top-N most-cited papers from top-tier venues
  // (CORE A/A* conferences or Scimago Q1-CS journals). Rendered as a
  // flat list without year grouping — ranked purely by impact.
  var SELECTED_TOP_N = 15;

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

  function publisherLabel(url) {
    // Best-effort host label for the "Publisher" link so readers know
    // where it goes without hovering. Falls back to "Publisher".
    if (!url) return "Publisher";
    if (url.indexOf("doi.org") !== -1) return "DOI";
    if (url.indexOf("aclanthology.org") !== -1) return "ACL Anthology";
    if (url.indexOf("openreview.net") !== -1) return "OpenReview";
    if (url.indexOf("openaccess.thecvf.com") !== -1) return "CVF";
    if (url.indexOf("proceedings.mlr.press") !== -1) return "PMLR";
    if (url.indexOf("dl.acm.org") !== -1) return "ACM";
    if (url.indexOf("ieeexplore.ieee.org") !== -1) return "IEEE";
    return "Publisher";
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
    if (pub.url_publisher) {
      parts.push(
        '<a class="pub-link pub-link-pub" href="' + escapeHtml(pub.url_publisher) +
        '" target="_blank" rel="noopener" title="Open the official publisher page">' +
        escapeHtml(publisherLabel(pub.url_publisher)) + ' ↗</a>'
      );
    }
    if (pub.url_arxiv) {
      parts.push(
        '<a class="pub-link pub-link-arxiv" href="' + escapeHtml(pub.url_arxiv) +
        '" target="_blank" rel="noopener" title="Open the arXiv preprint">arXiv ↗</a>'
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

  function isTopTier(pub) {
    return pub.type === "a_star_conf" || pub.type === "q1_journal";
  }

  // Sort by citations desc, then year desc. Used to pick the "top N"
  // in the Selected view and in the IEEE download.
  function byImpact(a, b) {
    var cb = (b.citations || 0) - (a.citations || 0);
    if (cb !== 0) return cb;
    return (b.year || 0) - (a.year || 0);
  }

  function matchesType(pub, typeFilter) {
    // "all" excludes preprints — they're only visible via the
    // dedicated Preprints tab. "selected" matches the top-tier
    // pool; the top-N slice is applied later at render time so
    // that the topic filter narrows the pool before ranking.
    if (typeFilter === "all") return pub.type !== "preprint";
    if (typeFilter === "selected") return isTopTier(pub);
    var types = FILTER_TYPES[typeFilter] || [typeFilter];
    return types.indexOf(pub.type) !== -1;
  }

  function selectedPubs(data) {
    // The set downloaded as IEEE bibliography — same definition and
    // ordering as the Selected view (top-N after topic filter is
    // applied, if any).
    return (data.publications || [])
      .filter(function (p) { return isTopTier(p) && matchesTopic(p, state.topic); })
      .sort(byImpact)
      .slice(0, SELECTED_TOP_N);
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
    // Same set and order as the on-page Selected view: top-N by
    // citations among CORE A/A* conferences and Scimago Q1-CS journals.
    var pubs = selectedPubs(data);
    var header = [
      "Publications — Fabrizio Silvestri",
      "Selected: top " + SELECTED_TOP_N + " most-cited papers in CORE A/A*",
      "conferences or Scimago Q1 (Computer Science) journals.",
      "Citations: Google Scholar (cached).",
      "Source: OpenAlex (https://openalex.org/authors/A5044165871)",
      "Generated: " + (data.last_updated || new Date().toISOString().slice(0, 10)),
      "Count: " + pubs.length,
      "",
      "References (IEEE style, in decreasing order of citations)",
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

  // ---- "More… / Less…" caps -------------------------------------------
  // Every list on the page shows at most CAP items until the visitor asks
  // for more. Expanded state is remembered per list until a filter changes.
  var CAP = 5;
  var expanded = {};

  function capList(container, itemSel, key) {
    if (!container) return;
    var toggleId = "more-" + key;
    var wrap = document.getElementById(toggleId);
    var items = container.querySelectorAll(itemSel);
    container.querySelectorAll(".is-extra").forEach(function (el) { el.classList.remove("is-extra"); });
    if (items.length <= CAP) {
      container.classList.remove("is-capped");
      if (wrap) wrap.remove();
      return;
    }
    for (var i = CAP; i < items.length; i++) items[i].classList.add("is-extra");
    // Year blocks and other children of the list that would show nothing
    // but a heading once collapsed are hidden too.
    Array.prototype.forEach.call(container.children, function (child) {
      if (child.matches(itemSel)) return;
      var inner = child.querySelectorAll(itemSel);
      var anyShown = Array.prototype.some.call(inner, function (el) { return !el.classList.contains("is-extra"); });
      if (!anyShown) child.classList.add("is-extra");
    });
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "more-toggle-wrap";
      wrap.id = toggleId;
      wrap.innerHTML = '<button type="button" class="more-toggle"></button>';
      container.insertAdjacentElement("afterend", wrap);
      wrap.firstChild.addEventListener("click", function () {
        expanded[key] = !expanded[key];
        applyCap(container, wrap, Number(wrap.dataset.total), key);
        if (!expanded[key]) container.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    }
    wrap.dataset.total = items.length;
    applyCap(container, wrap, items.length, key);
  }

  function applyCap(container, wrap, total, key) {
    var open = !!expanded[key];
    container.classList.toggle("is-capped", !open);
    var btn = wrap.firstChild;
    btn.textContent = open ? "Less\u2026" : "More\u2026 (" + (total - CAP) + ")";
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function render() {
    renderPubList();
    capList(byId("pub-list"), ".pub-item", "pubs");
  }

  function renderPubList() {
    var data = window.PUBLICATIONS;
    var list = byId("pub-list");
    if (!list) return;
    if (!data || !data.publications) {
      list.innerHTML = '<p class="pub-empty">No publication data found. Run scripts/fetch_publications.py.</p>';
      return;
    }

    var filtered = data.publications.filter(function (p) {
      return matchesType(p, state.type) && matchesTopic(p, state.topic);
    });

    // Selected view: flat, citation-ranked, capped at SELECTED_TOP_N.
    // No year grouping, no recent/older split — the list is a
    // signature-paper highlight reel.
    if (state.type === "selected") {
      var top = filtered.slice().sort(byImpact).slice(0, SELECTED_TOP_N);
      if (top.length === 0) {
        list.innerHTML = '<p class="pub-empty">No publications match the current filters.</p>';
        return;
      }
      list.innerHTML = '<div class="pub-year-block">' + top.map(renderItem).join("") + '</div>';
      return;
    }

    // Rolling 5-year window anchored on the most-recent year across the
    // full corpus (so the window doesn't shrink when a topic filter
    // happens to exclude the newest papers).
    var max = maxYear(data);
    var cutoff = max - (RECENT_YEARS - 1);

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

    var citEl = byId("cit-last-updated");
    var citWrap = byId("cit-last-updated-wrap");
    if (citEl && citWrap) {
      var when = data.citations_fetched_at || "";
      if (when) {
        citEl.textContent = when;
        citWrap.hidden = false;
      } else {
        citWrap.hidden = true;
      }
    }
  }

  function setTypeFilter(value) {
    state.type = value;
    expanded.pubs = false;
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
    expanded.pubs = false;
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

  function renderAwards() {
    var data = window.PUBLICATIONS;
    var list = byId("awards-list");
    var section = byId("awards");
    var navItem = byId("nav-awards");
    if (!list || !section) return;
    var awards = (data && data.awards) || [];
    if (awards.length === 0) {
      section.hidden = true;
      if (navItem) navItem.hidden = true;
      return;
    }
    list.innerHTML = awards.map(function (a) {
      var title = escapeHtml(a.title);
      if (a.url) {
        title = '<a href="' + escapeHtml(a.url) + '" target="_blank" rel="noopener">' + title + ' ↗</a>';
      }
      var meta = [];
      if (a.issuer) meta.push(escapeHtml(a.issuer));
      if (a.description) meta.push(escapeHtml(a.description));
      return (
        '<li class="award-item">' +
          '<span class="award-year">' + a.year + '</span>' +
          '<div class="award-body">' +
            '<div class="award-title">' + title + '</div>' +
            (meta.length ? '<div class="award-meta">' + meta.join(' · ') + '</div>' : '') +
          '</div>' +
        '</li>'
      );
    }).join("");
    section.hidden = false;
    if (navItem) navItem.hidden = false;
  }

  function renderTalks() {
    var data = window.PUBLICATIONS;
    var list = byId("talks-list");
    var section = byId("talks");
    var navItem = byId("nav-talks");
    if (!list || !section) return;
    var talks = (data && data.talks) || [];
    if (talks.length === 0) {
      section.hidden = true;
      if (navItem) navItem.hidden = true;
      return;
    }
    list.innerHTML = talks.map(function (t) {
      var title = escapeHtml(t.title);
      if (t.url) {
        title = '<a href="' + escapeHtml(t.url) + '" target="_blank" rel="noopener">' + title + ' ↗</a>';
      }
      var meta = [];
      if (t.venue) meta.push(escapeHtml(t.venue));
      if (t.location) meta.push(escapeHtml(t.location));
      var roleBadge = t.role
        ? '<span class="talk-role">' + escapeHtml(t.role) + '</span>'
        : '';
      return (
        '<li class="talk-item">' +
          '<span class="talk-year">' + t.year + '</span>' +
          '<div class="talk-body">' +
            '<div class="talk-title">' + title + roleBadge + '</div>' +
            (meta.length ? '<div class="talk-meta">' + meta.join(' · ') + '</div>' : '') +
          '</div>' +
        '</li>'
      );
    }).join("");
    section.hidden = false;
    if (navItem) navItem.hidden = false;
  }

  function renderServices() {
    var data = window.PUBLICATIONS;
    var wrap = byId("services-groups");
    var section = byId("services");
    var navItem = byId("nav-services");
    if (!wrap || !section) return;
    var groups = (data && data.services) || [];
    if (groups.length === 0) {
      section.hidden = true;
      if (navItem) navItem.hidden = true;
      return;
    }
    wrap.innerHTML = groups.map(function (g) {
      var items = (g.items || []).map(function (i) {
        var title = escapeHtml(i.title);
        if (i.url) {
          title = '<a href="' + escapeHtml(i.url) + '" target="_blank" rel="noopener">' + title + ' \u2197</a>';
        }
        var role = i.role
          ? '<span class="service-role">' + escapeHtml(i.role) + '</span>'
          : '';
        return (
          '<li class="service-item">' +
            '<span class="service-year">' + (i.year ? i.year : '') + '</span>' +
            '<div class="service-body">' +
              '<div class="service-title">' + title + role + '</div>' +
              (i.detail ? '<div class="service-detail">' + escapeHtml(i.detail) + '</div>' : '') +
            '</div>' +
          '</li>'
        );
      }).join("");
      // Groups with no years at all (editorial boards) drop the year
      // gutter so their titles start at the card's left edge.
      var hasYear = (g.items || []).some(function (i) { return !!i.year; });
      var listClass = "service-list" + (hasYear ? "" : " service-list-noyear");
      return (
        '<article class="card service-group">' +
          '<h3>' + escapeHtml(g.group) + '</h3>' +
          (g.note ? '<p class="service-note">' + escapeHtml(g.note) + '</p>' : '') +
          (items ? '<ul class="' + listClass + '">' + items + '</ul>' : '') +
        '</article>'
      );
    }).join("");
    section.hidden = false;
    if (navItem) navItem.hidden = false;
  }

  // Fetch publications.json with cache: 'no-store' so visitors always see
  // the latest bot refresh (counts, list, awards, talks, services) even when their
  // browser or an intermediate cache is still serving an older index.html.
  // Falls back to a window.PUBLICATIONS preloaded by an inline script if
  // the fetch fails (offline, file moved, etc.).
  function loadData() {
    return fetch("data/publications.json", { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (json) { window.PUBLICATIONS = json; })
      .catch(function (err) {
        if (window.PUBLICATIONS) return; // use whatever was preloaded
        console.error("publications.json fetch failed:", err);
      });
  }

  // Homepage "Recent publications" panel: the newest top-tier papers
  // (CORE A/A* conferences, Scimago Q1 journals), newest year first and
  // most-cited first within a year. Refreshes with the nightly sync.
  var RECENT_N = 4;
  function shortAuthors(authors) {
    return (authors || []).map(function (a) {
      var parts = String(a).trim().split(/\s+/);
      return parts[parts.length - 1];
    }).join(", ");
  }
  function renderRecent() {
    var list = byId("recent-list");
    var data = window.PUBLICATIONS;
    if (!list || !data) return;
    var pubs = (data.publications || [])
      .filter(isTopTier)
      .sort(function (a, b) {
        return ((b.year || 0) - (a.year || 0)) || ((b.citations || 0) - (a.citations || 0));
      })
      .slice(0, RECENT_N);
    if (!pubs.length) { list.innerHTML = ""; return; }
    list.innerHTML = pubs.map(function (p) {
      var yy = p.year ? " '" + String(p.year).slice(-2) : "";
      var title = escapeHtml(p.title);
      if (p.url) {
        title = '<a href="' + escapeHtml(p.url) + '" target="_blank" rel="noopener">' + title + "</a>";
      }
      return '<li><span class="recent-venue">' + escapeHtml((p.venue_short || TYPE_FALLBACK[p.type] || "") + yy) +
        '</span><span class="recent-title">' + title +
        '</span><span class="recent-authors">' + escapeHtml(shortAuthors(p.authors)) + "</span></li>";
    }).join("");
  }

  // Links elsewhere on the page (e.g. the research questions) that jump to
  // the publication list pre-filtered by topic: <a data-topic-link="ir">.
  function initTopicLinks() {
    document.addEventListener("click", function (e) {
      var link = e.target.closest("[data-topic-link]");
      if (!link) return;
      e.preventDefault();
      if (state.type === "selected") setTypeFilter("all");
      setTopicFilter(link.getAttribute("data-topic-link"));
      var pubs = byId("publications");
      if (pubs) pubs.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function renderAll() {
    if (!window.PUBLICATIONS) return; // nothing to render
    updateStats();
    initTypeTabs();
    initTopicTabs();
    initChipClicks();
    initDownloadButton();
    renderAwards();
    renderTalks();
    renderServices();
    capList(byId("awards-list"), ".award-item", "awards");
    capList(byId("talks-list"), ".talk-item", "talks");
    document.querySelectorAll("#services-groups .service-list").forEach(function (ul, i) {
      capList(ul, ".service-item", "services-" + i);
    });
    renderRecent();
    initTopicLinks();
    render();
  }

  document.addEventListener("DOMContentLoaded", function () {
    loadData().then(renderAll);
  });
})();
