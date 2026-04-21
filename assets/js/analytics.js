/* Google Analytics 4 with GDPR Consent Mode v2.
 *
 * - Loads the gtag.js library unconditionally but sets `analytics_storage`
 *   to "denied" as the default consent state. Until the visitor consents,
 *   GA4 runs in cookieless "ping" mode — no cookies, no PII, no behavioural
 *   profiling. On accept, consent is upgraded to "granted" and the first
 *   full pageview fires retroactively.
 * - Persists the visitor's decision in localStorage so the banner shows
 *   only once per browser.
 * - Guards on GA4_ID: if it's still the placeholder, analytics bootstrap
 *   is skipped entirely (no stray network request, no banner).
 *
 * To activate: replace GA4_ID with the Measurement ID from Google
 * Analytics → Admin → Data Streams → Web → Measurement ID (starts with
 * "G-").
 */
(function () {
  "use strict";

  var GA4_ID = "G-XXXXXXXXXX"; // <-- replace with your real ID
  var STORAGE_KEY = "analytics-consent"; // "granted" | "denied" | null

  if (!GA4_ID || GA4_ID === "G-XXXXXXXXXX") return; // Not configured

  var stored = null;
  try { stored = localStorage.getItem(STORAGE_KEY); } catch (e) { /* private mode */ }

  // Bootstrap gtag BEFORE gtag.js loads so the default consent state is
  // in place the moment the library initialises.
  window.dataLayer = window.dataLayer || [];
  function gtag() { window.dataLayer.push(arguments); }
  window.gtag = gtag;

  gtag("js", new Date());
  gtag("consent", "default", {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    analytics_storage: "denied",
    functionality_storage: "granted",
    security_storage: "granted",
    wait_for_update: 500,
  });
  if (stored === "granted") {
    gtag("consent", "update", { analytics_storage: "granted" });
  }
  gtag("config", GA4_ID, { anonymize_ip: true });

  var s = document.createElement("script");
  s.async = true;
  s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(GA4_ID);
  document.head.appendChild(s);

  function setConsent(decision) {
    try { localStorage.setItem(STORAGE_KEY, decision); } catch (e) { /* ignore */ }
    if (decision === "granted") {
      gtag("consent", "update", { analytics_storage: "granted" });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var banner = document.getElementById("cookie-banner");
    if (!banner) return;
    if (!stored) banner.hidden = false;

    var accept = document.getElementById("cookie-accept");
    var decline = document.getElementById("cookie-decline");
    if (accept) accept.addEventListener("click", function () {
      setConsent("granted");
      banner.hidden = true;
    });
    if (decline) decline.addEventListener("click", function () {
      setConsent("denied");
      banner.hidden = true;
    });
  });
})();
