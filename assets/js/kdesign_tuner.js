/* K-Design Tuner v1
   - Controls CSS variables on <html.kdesign_bright>
   - Persists to localStorage
*/
(() => {
  const KEY = "sk_kdesign_tuner_v1";
  const root = document.documentElement;

  function isKDesign() {
    return root.classList.contains("kdesign_bright");
  }

  const DEFAULTS = {
    "--kd-bg-strength": 0.55,
    "--kd-card-alpha": 0.78,
    "--kd-inner-alpha": 0.62,
    "--kd-muted-alpha": 0.62,
    "--kd-demo-dark": 0.32,
    "--kd-demo-dark2": 0.42,
    "--kd-demo-text": 0.78,
  };

  function applyAll(map) {
    if (!isKDesign()) return;
    for (const k of Object.keys(DEFAULTS)) {
      const v = map && map[k] != null ? map[k] : DEFAULTS[k];
      root.style.setProperty(k, String(v));
    }
  }

  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch { return null; }
  }

  function save(map) {
    try { localStorage.setItem(KEY, JSON.stringify(map)); } catch {}
  }

  function clamp(n, a=0, b=1) {
    n = Number(n);
    if (Number.isNaN(n)) return a;
    return Math.max(a, Math.min(b, n));
  }

  function ui() {
    const wrap = document.createElement("div");
    wrap.id = "kdesign-tuner";
    wrap.style.cssText = `
      position: fixed; right: 18px; bottom: 18px; z-index: 999999;
      width: 260px; border-radius: 16px; padding: 12px 12px 10px;
      background: rgba(255,255,255,.78);
      border: 1px solid rgba(20,16,40,.14);
      box-shadow: 0 20px 60px rgba(25,15,60,.14);
      backdrop-filter: blur(14px);
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
      color: #0f0b2e;
    `;

    wrap.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
        <div style="font-weight:800;">K-Design Tuner</div>
        <div style="margin-left:auto;opacity:.6;font-size:11px;">live</div>
      </div>
      <div id="kdt-body" style="display:grid;gap:10px;"></div>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:10px;">
        <button id="kdt-reset" style="padding:8px 10px;border-radius:12px;border:1px solid rgba(20,16,40,.14);background:transparent;cursor:pointer;">リセット</button>
        <button id="kdt-close" style="padding:8px 10px;border-radius:12px;border:1px solid rgba(20,16,40,.14);background:rgba(15,11,46,.06);cursor:pointer;">閉じる</button>
      </div>
    `;

    const body = wrap.querySelector("#kdt-body");

    const items = [
      { key: "--kd-bg-strength", label: "背景の濃さ", min: 0.10, max: 0.90, step: 0.01 },
      { key: "--kd-card-alpha",  label: "カード透明度", min: 0.45, max: 0.95, step: 0.01 },
      { key: "--kd-inner-alpha", label: "内側透明度",   min: 0.35, max: 0.95, step: 0.01 },
      { key: "--kd-muted-alpha", label: "説明文の濃さ", min: 0.35, max: 0.95, step: 0.01 },
      { key: "--kd-demo-dark",   label: "暗箱の暗さ①", min: 0.00, max: 0.85, step: 0.01 },
      { key: "--kd-demo-dark2",  label: "暗箱の暗さ②", min: 0.00, max: 0.90, step: 0.01 },
      { key: "--kd-demo-text",   label: "暗箱内テキスト", min: 0.35, max: 1.00, step: 0.01 },
    ];

    const state = load() || { ...DEFAULTS };

    function row(it) {
      const r = document.createElement("div");
      r.innerHTML = `
        <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:4px;">
          <div style="font-size:12px;font-weight:700;">${it.label}</div>
          <div style="margin-left:auto;font-size:12px;opacity:.7;" data-val></div>
        </div>
        <input type="range" min="${it.min}" max="${it.max}" step="${it.step}" value="${state[it.key] ?? DEFAULTS[it.key]}">
      `;
      const inp = r.querySelector("input");
      const val = r.querySelector("[data-val]");
      const refresh = () => {
        const v = clamp(inp.value, Number(it.min), Number(it.max));
        inp.value = String(v);
        val.textContent = v.toFixed(2);
        state[it.key] = v;
        applyAll(state);
        save(state);
      };
      inp.addEventListener("input", refresh);
      refresh();
      return r;
    }

    items.forEach(it => body.appendChild(row(it)));

    wrap.querySelector("#kdt-reset").onclick = () => {
      for (const k of Object.keys(DEFAULTS)) state[k] = DEFAULTS[k];
      applyAll(state);
      save(state);
      // re-render values
      wrap.remove();
      ui();
    };
    wrap.querySelector("#kdt-close").onclick = () => wrap.remove();

    document.body.appendChild(wrap);
    applyAll(state);
  }

  // Boot
  const boot = () => {
    if (!isKDesign()) return;
    applyAll(load());
    // show tuner by default (you can change this behavior later)
    ui();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
