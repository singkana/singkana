/* SingKANA Analytics (TikTok funnel) v1
 * - utm_* / ttclid を localStorage に保存
 * - /api/attribution に1回送信（sentフラグ）
 * - /api/track にフロントイベント送信
 *  - TRY/CONVERT: landing_click / convert_click
 *  - 変換成功: convert_success（サーバ側でも二重OK）
 *  - コピー/エクスポート: copy_export
 *  - PRO購入/請求管理: billing_open
 */
(function () {
  if (window.__SINGKANA_ANALYTICS__) return;
  window.__SINGKANA_ANALYTICS__ = true;

  var LS_ATTR = "sk_attr_v1";
  var LS_ATTR_SENT = "sk_attr_sent_v1";

  function safeJsonParse(s, fallback) {
    try { return JSON.parse(s); } catch (e) { return fallback; }
  }

  function getAttr() {
    try {
      var raw = localStorage.getItem(LS_ATTR);
      return raw ? safeJsonParse(raw, {}) : {};
    } catch (e) {
      return {};
    }
  }

  function setAttr(obj) {
    try { localStorage.setItem(LS_ATTR, JSON.stringify(obj || {})); } catch (e) {}
  }

  function getRefHost() {
    try {
      if (!document.referrer) return "";
      var u = new URL(document.referrer);
      return u.hostname || "";
    } catch (e) {
      return "";
    }
  }

  function postJson(url, payload) {
    try {
      var body = JSON.stringify(payload || {});
      if (navigator.sendBeacon) {
        try {
          var blob = new Blob([body], { type: "application/json" });
          var ok = navigator.sendBeacon(url, blob);
          if (ok) return Promise.resolve(true);
        } catch (e) {}
      }
      return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        keepalive: true,
        body: body
      }).then(function () { return true; }).catch(function () { return false; });
    } catch (e) {
      return Promise.resolve(false);
    }
  }

  function track(name, props) {
    var attr = getAttr();
    var payload = {
      name: String(name || ""),
      props: Object.assign({
        path: location.pathname,
        ref_host: getRefHost(),
        ts: Date.now()
      }, (attr || {}), (props && typeof props === "object" ? props : {}))
    };
    return postJson("/api/track", payload);
  }

  function captureAttributionOnce() {
    var params;
    try { params = new URLSearchParams(location.search || ""); } catch (e) { params = null; }
    if (!params) return;

    var keys = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "ttclid"];
    var found = {};
    var hasAny = false;
    keys.forEach(function (k) {
      var v = params.get(k);
      if (v && String(v).trim()) {
        found[k] = String(v).trim();
        hasAny = true;
      }
    });

    if (!hasAny) return;

    // localStorageに保存（後から遷移しても残す）
    var merged = Object.assign({}, getAttr(), found);
    setAttr(merged);

    // 1回だけ送信（sentフラグ）
    var sent = false;
    try { sent = localStorage.getItem(LS_ATTR_SENT) === "1"; } catch (e) {}
    if (sent) return;

    postJson("/api/attribution", Object.assign({}, merged, { landing_path: location.pathname }))
      .then(function () {
        try { localStorage.setItem(LS_ATTR_SENT, "1"); } catch (e) {}
      });
  }

  function wrapGlobal(fnName, before, after) {
    try {
      var orig = window[fnName];
      if (typeof orig !== "function") return;
      if (orig.__sk_wrapped__) return;
      function wrapped() {
        var args = arguments;
        try { if (before) before.apply(null, args); } catch (e) {}
        var ret;
        try { ret = orig.apply(this, args); } catch (e) { throw e; }
        try { if (after) after.apply(null, [ret].concat([].slice.call(args))); } catch (e) {}
        return ret;
      }
      wrapped.__sk_wrapped__ = true;
      window[fnName] = wrapped;
    } catch (e) {}
  }

  function bindClicks() {
    // TRY (hero → studio)
    try {
      var links = document.querySelectorAll('a[href="#studio"]');
      links.forEach(function (a) {
        a.addEventListener("click", function () {
          track("landing_click", { kind: "anchor_studio" });
        }, { capture: true });
      });
    } catch (e) {}

    // convert click / success (wrap existing convertLyrics)
    wrapGlobal("convertLyrics",
      function () {
        track("convert_click", { kind: "convert_btn" });
      },
      function () {
        try {
          var ok = Array.isArray(window.currentConvertedLines) ? window.currentConvertedLines.length > 0 : false;
          if (ok) track("convert_success", { via: "client_convert" });
        } catch (e) {}
      }
    );

    // copy/export
    ["copyKanaOnly", "copyEnKana", "downloadTxt", "downloadSrt"].forEach(function (fn) {
      wrapGlobal(fn, function () {
        track("copy_export", { action: fn });
      }, null);
    });

    // billing open
    wrapGlobal("startCheckout", function (plan) {
      track("billing_open", { action: "checkout", plan: String(plan || "") });
    }, null);
    wrapGlobal("openBillingPortal", function () {
      track("billing_open", { action: "portal" });
    }, null);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      captureAttributionOnce();
      bindClicks();
    }, { once: true });
  } else {
    captureAttributionOnce();
    bindClicks();
  }
})();

