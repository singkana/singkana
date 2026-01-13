/* SingKANA Paywall Gate v1.3 (UI Gate + optional fetch gate)
   - 非Basic（Natural/Precise等）を選んだ瞬間にPaywallを出して basic に戻す
   - 将来 /api/convert を叩く実装になっても 402 で拾えるよう fetch gate も残す
*/
(function () {
  if (window.__SINGKANA_PAYWALL_GATE__) return;
  window.__SINGKANA_PAYWALL_GATE__ = true;

  function show(detail) {
    if (document.getElementById("sk-paywall-overlay")) return;

    var ov = document.createElement("div");
    ov.id = "sk-paywall-overlay";
    ov.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:99999;display:flex;align-items:center;justify-content:center;padding:24px;";

    var card = document.createElement("div");
    card.style.cssText = "max-width:520px;width:100%;background:#0b0f19;color:#e5e7eb;border:1px solid rgba(255,255,255,.12);border-radius:16px;padding:18px;box-shadow:0 12px 40px rgba(0,0,0,.35);font-family:system-ui,-apple-system,Segoe UI,sans-serif;";

    var title = document.createElement("div");
    title.textContent = "Pro機能です";
    title.style.cssText = "font-size:18px;font-weight:700;margin:0 0 8px 0;";

    var msg = document.createElement("div");
    var mode = (detail && detail.requested_mode) ? String(detail.requested_mode) : "pro";
    msg.textContent = "選択したモード（" + mode + "）はProプランで利用できます。";
    msg.style.cssText = "opacity:.92;line-height:1.5;margin:0 0 14px 0;";

    var row = document.createElement("div");
    row.style.cssText = "display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap;";

    var close = document.createElement("button");
    close.type = "button";
    close.textContent = "閉じる";
    close.style.cssText = "padding:10px 14px;border-radius:12px;border:1px solid rgba(255,255,255,.15);background:transparent;color:#e5e7eb;cursor:pointer;";
    close.onclick = function () { ov.remove(); };

    var go = document.createElement("a");
    go.textContent = "料金を見る";
    go.href = "/#pricing";
    go.style.cssText = "padding:10px 14px;border-radius:12px;border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.08);color:#e5e7eb;text-decoration:none;display:inline-block;";

    row.appendChild(close);
    row.appendChild(go);

    card.appendChild(title);
    card.appendChild(msg);
    card.appendChild(row);
    ov.appendChild(card);

    ov.addEventListener("click", function (e) { if (e.target === ov) ov.remove(); });
    document.body.appendChild(ov);
  }

  function norm(v){ return String(v||"").toLowerCase().trim(); }
  function isFree(v){ return norm(v) === "basic"; }

  function bindUIGate() {
    var el = document.getElementById("displayMode");
    if (!el) return;

    el.addEventListener("change", function () {
      var v = norm(el.value);
      if (!isFree(v)) {
        // basicへ戻す（UIの整合性）
        el.value = "basic";
        try { el.dispatchEvent(new Event("change")); } catch (e) {}
        show({ requested_mode: v });
      }
    }, true);
  }

  // fetch gate（将来 /api/convert を叩くようになっても拾う）
  var origFetch = window.fetch ? window.fetch.bind(window) : null;
  if (origFetch) {
    window.fetch = async function (input, init) {
      var res = await origFetch(input, init);
      try {
        var url = (typeof input === "string") ? input : (input && input.url) ? input.url : "";
        if (url && url.indexOf("/api/convert") !== -1 && res.status === 402) {
          var detail = {};
          try { detail = await res.clone().json(); } catch (e) {}
          show(detail);
        }
      } catch (e) {}
      return res;
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindUIGate, { once: true });
  } else {
    bindUIGate();
  }
})();
