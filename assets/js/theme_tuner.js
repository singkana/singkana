/* SingKANA Theme Tuner (kdesign_bright)
   - Press Alt+T to toggle
   - Saves to localStorage: sk_theme_tuner
*/
(() => {
  const KEY = "sk_theme_tuner";
  const root = document.documentElement;

  function isKDesign() {
    return root.classList.contains("kdesign_bright");
  }

  const defaults = {
    bgStrength: 0.45,   // 背景グラデの濃さ（0-1）
    glassAlpha: 0.78,   // 白ガラスの濃さ（0-1）
    glassBlur: 18,      // blur(px)
    inkAlpha: 1.0,      // 文字の濃さ（0-1）
    mutedAlpha: 0.62,   // サブ文字（0-1）
    cardTint: 0.00      // カードに色味を足す（0-0.12くらいが実用）
  };

  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return { ...defaults };
      const obj = JSON.parse(raw);
      return { ...defaults, ...obj };
    } catch {
      return { ...defaults };
    }
  }

  function save(state) {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch {}
  }

  function apply(state) {
    if (!isKDesign()) return;

    root.style.setProperty("--k-bg-strength", String(state.bgStrength));
    root.style.setProperty("--k-glass-alpha", String(state.glassAlpha));
    root.style.setProperty("--k-glass-blur", String(state.glassBlur) + "px");
    root.style.setProperty("--k-ink-alpha", String(state.inkAlpha));
    root.style.setProperty("--k-muted-alpha", String(state.mutedAlpha));
    root.style.setProperty("--k-card-tint", String(state.cardTint));
  }

  function buildUI(state) {
    const wrap = document.createElement("div");
    wrap.id = "sk-theme-tuner";
    wrap.style.cssText = `
      position:fixed;right:16px;bottom:16px;z-index:999999;
      width:320px;max-width:calc(100vw - 32px);
      background:rgba(255,255,255,.72);
      border:1px solid rgba(20,16,40,.16);
      border-radius:16px;
      box-shadow:0 18px 70px rgba(25,15,60,.18);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      padding:14px 14px 12px;
      font-family:system-ui,-apple-system,Segoe UI,sans-serif;
      color:rgba(15,11,46,.95);
    `;

    const title = document.createElement("div");
    title.textContent = "Theme Tuner (Alt+T)";
    title.style.cssText = "font-weight:800;margin:0 0 10px 0;font-size:13px;";
    wrap.appendChild(title);

    function row(label, min, max, step, key) {
      const r = document.createElement("div");
      r.style.cssText = "display:grid;grid-template-columns:1fr 90px;gap:10px;align-items:center;margin:8px 0;";
      const l = document.createElement("div");
      l.textContent = label;
      l.style.cssText = "font-size:12px;opacity:.9;";
      const v = document.createElement("input");
      v.type = "range";
      v.min = String(min);
      v.max = String(max);
      v.step = String(step);
      v.value = String(state[key]);
      v.oninput = () => {
        const val = key.includes("Blur") ? parseFloat(v.value) : parseFloat(v.value);
        state[key] = val;
        apply(state);
        save(state);
      };
      r.appendChild(l);
      r.appendChild(v);
      return r;
    }

    wrap.appendChild(row("背景の濃さ", 0.20, 0.85, 0.01, "bgStrength"));
    wrap.appendChild(row("ガラスの白さ", 0.55, 0.92, 0.01, "glassAlpha"));
    wrap.appendChild(row("ガラスのblur", 0, 28, 1, "glassBlur"));
    wrap.appendChild(row("文字の濃さ", 0.70, 1.00, 0.01, "inkAlpha"));
    wrap.appendChild(row("サブ文字", 0.45, 0.75, 0.01, "mutedAlpha"));
    wrap.appendChild(row("カード色味", 0.00, 0.12, 0.005, "cardTint"));

    const btns = document.createElement("div");
    btns.style.cssText = "display:flex;gap:10px;justify-content:flex-end;margin-top:10px;";

    const reset = document.createElement("button");
    reset.textContent = "リセット";
    reset.style.cssText = "padding:8px 12px;border-radius:12px;border:1px solid rgba(20,16,40,.16);background:transparent;cursor:pointer;font-weight:700;";
    reset.onclick = () => {
      Object.assign(state, { ...defaults });
      apply(state);
      save(state);
      // 再描画せずレンジだけ合わせる
      wrap.querySelectorAll("input[type=range]").forEach((inp) => {
        const label = inp.parentElement?.firstChild?.textContent || "";
        const map = {
          "背景の濃さ":"bgStrength","ガラスの白さ":"glassAlpha","ガラスのblur":"glassBlur",
          "文字の濃さ":"inkAlpha","サブ文字":"mutedAlpha","カード色味":"cardTint"
        };
        const k = map[label];
        if (k) inp.value = String(state[k]);
      });
    };

    const close = document.createElement("button");
    close.textContent = "閉じる";
    close.style.cssText = "padding:8px 12px;border-radius:12px;border:1px solid rgba(20,16,40,.16);background:rgba(15,11,46,.08);cursor:pointer;font-weight:800;";
    close.onclick = () => wrap.remove();

    btns.appendChild(reset);
    btns.appendChild(close);
    wrap.appendChild(btns);

    return wrap;
  }

  function toggle() {
    const ex = document.getElementById("sk-theme-tuner");
    if (ex) { ex.remove(); return; }
    if (!isKDesign()) return; // kdesign_bright 以外では出さない
    const state = load();
    apply(state);
    document.body.appendChild(buildUI(state));
  }

  // boot: apply saved immediately
  const init = () => {
    const state = load();
    apply(state);
    window.addEventListener("keydown", (e) => {
      if (e.altKey && (e.key === "t" || e.key === "T")) {
        e.preventDefault();
        toggle();
      }
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
