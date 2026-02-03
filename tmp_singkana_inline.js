
    // =========================
    // Global State
    // =========================
    window.currentConvertedLines = [];  // ← displayMode再描画のため、グローバルに確実に置く
    window.activeIndex = -1;
    let currentActiveBlock = null;

    // =========================
    // Plan Gate (Free / Pro)
    // =========================
    const PLAN = {
      tier: "free", // "free" | "pro"
      devProOverride: false // 開発者モードフラグ
    };

    function isPro() {
      return PLAN.tier === "pro";
    }

    // 開発者モード状態を取得（ページ読み込み時）
    async function loadUserPlan() {
      try {
        // URLパラメータから dev_pro トークンを取得
        const urlParams = new URLSearchParams(window.location.search);
        const devProToken = urlParams.get("dev_pro");
        
        // dev_pro トークンがある場合は /api/me に渡す
        const apiUrl = devProToken ? `/api/me?dev_pro=${encodeURIComponent(devProToken)}` : "/api/me";
        
        const res = await fetch(apiUrl);
        const data = await res.json();
        console.log("[loadUserPlan] API response:", data); // デバッグ用
        
        if (data.ok) {
          PLAN.tier = data.plan || "free";
          PLAN.devProOverride = data.dev_pro_override || false;
          
          console.log("[loadUserPlan] PLAN:", PLAN); // デバッグ用
          
          // 開発者モードバッジを表示
          const badge = document.getElementById("dev-pro-badge");
          console.log("[loadUserPlan] Badge element:", badge); // デバッグ用
          
          if (badge) {
            if (PLAN.devProOverride) {
              console.log("[loadUserPlan] Showing badge"); // デバッグ用
              badge.classList.remove("hidden");
            } else {
              console.log("[loadUserPlan] Hiding badge"); // デバッグ用
              badge.classList.add("hidden");
            }
          } else {
            console.warn("[loadUserPlan] Badge element not found!");
          }
          
          // 精密モードの選択肢を更新（Freeの場合は無効化）
          const preciseOption = document.querySelector('#displayMode option[value="precise"]');
          if (preciseOption) {
            if (isPro()) {
              preciseOption.removeAttribute('disabled');
              preciseOption.textContent = '精密（日本語として歌う・最適・失敗したくない人向け）';
            } else {
              preciseOption.setAttribute('disabled', 'disabled');
              preciseOption.textContent = '精密（日本語として歌う・最適・失敗したくない人向け） [Pro]';
            }
          }
        }
      } catch (e) {
        console.warn("Failed to load user plan:", e);
      }
    }

    function guardDisplayMode(mode) {
      if (isPro()) return true;

      // Freeでは精密モードのみ制限（Naturalは利用可能）
      if (mode === "precise") {
        alert("精密モード（日本語として歌う・最適）は Pro プランで利用できます。\n\nFree では Basic / Natural が利用可能です。");
        const sel = document.getElementById("displayMode");
        if (sel) sel.value = "natural"; // Naturalに戻す
        return false;
      }
      return true;
    }

    // =========================
    // Tabs
    // =========================
    function setResultPlaceholderState(){
      const rp = document.getElementById("result-panel");
      if (!rp) return;
      const onlyP = rp.children.length === 1 && rp.firstElementChild && rp.firstElementChild.tagName === "P";
      rp.classList.toggle("is-placeholder", !!onlyP);
    }

    document.addEventListener("DOMContentLoaded", () => {
      // ユーザープラン（開発者モード含む）を読み込み
      loadUserPlan();
      
      const tabButtons = document.querySelectorAll(".tab-btn");
      const panels = {
        result: document.getElementById("tab-result"),
        feedback: document.getElementById("tab-feedback"),
      };

      tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
          const tab = btn.dataset.tab;
          tabButtons.forEach(b => b.classList.toggle("active", b === btn));
          Object.entries(panels).forEach(([key, panel]) => {
            const active = key === tab;
            panel.classList.toggle("active", active);
            panel.classList.toggle("hidden", !active);
          });
        });
      });

      // 起動時に復元（localStorage）
      restoreStudioState(true);
      setResultPlaceholderState();

      // 自動保存
      const songEl = document.getElementById("song-title");
      const lyrEl  = document.getElementById("lyrics-input");
      const fbEl   = document.getElementById("feedback-text");

      let t = null;
      function scheduleAutoSave(){
        if (t) clearTimeout(t);
        t = setTimeout(() => saveStudioState(true), 450);
      }
      [songEl, lyrEl, fbEl].forEach(el => {
        if (!el) return;
        el.addEventListener("input", scheduleAutoSave);
        el.addEventListener("change", scheduleAutoSave);
      });

      // DisplayMode restore/persist
      const dm = document.getElementById("displayMode");
      if (dm) {
        const saved = localStorage.getItem("displayMode");
        if (saved) dm.value = saved;
        dm.addEventListener("change", () => {
          const mode = dm.value;
          if (!guardDisplayMode(mode)) return;

          try { localStorage.setItem("displayMode", mode); } catch(e){}
          __displayModeChangeHandler();
        });
      }
    });

    // =========================
    // Romaji (API)
    // =========================
    (function(){
      const $in = document.getElementById("romaji_in");
      const $out = document.getElementById("romaji_out");
      const $go = document.getElementById("romaji_go");
      const $copy = document.getElementById("romaji_copy");
      const $st = document.getElementById("romaji_status");

      if (!$in || !$out || !$go || !$copy || !$st) return;

      async function convert(){
        const text = ($in.value || "").trim();
        if(!text){ $st.textContent = "歌詞を貼ってください"; return; }
        $st.textContent = "変換中…";
        $out.value = "";

        try{
          const res = await fetch("/api/romaji", {
            method: "POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({text})
          });
          const j = await res.json().catch(()=> ({}));
          if(!res.ok || !j.ok){
            // 無料制限エラーの場合は特別なメッセージ
            if(res.status === 402 && j.code === "payment_required"){
              $st.textContent = `無料制限: ${j.message || "Proプランが必要です"}`;
            } else {
              $st.textContent = "エラー: " + (j.message || j.error || res.status);
            }
            return;
          }
          $out.value = j.romaji || "";
          // メタ情報があれば表示
          if(j.meta && j.meta.free_limit){
            $st.textContent = `完了 (${j.meta.text_length}/${j.meta.free_limit}文字)`;
          } else {
            $st.textContent = "完了";
          }
        }catch(e){
          $st.textContent = "ネットワークエラー";
        }
      }

      async function copy(){
        const v = ($out.value || "").trim();
        if(!v){ $st.textContent = "コピーする内容がありません"; return; }
        try{
          await navigator.clipboard.writeText(v);
          $st.textContent = "コピーしました";
        }catch(e){
          $st.textContent = "コピー失敗（ブラウザ制限）";
        }
      }

      $go.addEventListener("click", convert);
      $copy.addEventListener("click", copy);
    })();

    // =========================
    // Studio Save/Restore/Templates
    // =========================
    const LS_KEY = "singkana.studio.v1";
    const TEMPLATES = {
      warmup: { title: "warmup", lyrics: ["Take it easy, keep it steady","Breathe in slow, breathe out ready","Hold the note and let it glow"].join("\n") },
      chorus: { title: "chorus-practice", lyrics: ["We are rising, we are shining","In the night, we keep on flying","Let it go, and sing it loud"].join("\n") },
      speech: { title: "consonants", lyrics: ["Just a little bit, step by step","Keep the beat, don't stop, don't slip","Bright light, night ride, right side"].join("\n") }
    };

    function setStudioStatus(msg) {
      const el = document.getElementById("studio-status");
      if (!el) return;
      el.textContent = msg || "";
      if (msg) setTimeout(() => { el.textContent = ""; }, 2200);
    }

    function readStudioStateFromUI() {
      const song = (document.getElementById("song-title")?.value || "").toString();
      const lyrics = (document.getElementById("lyrics-input")?.value || "").toString();
      const feedback = (document.getElementById("feedback-text")?.value || "").toString();
      return { song, lyrics, feedback, ts: new Date().toISOString() };
    }

    function writeStudioStateToUI(st) {
      if (!st) return;
      const songEl = document.getElementById("song-title");
      const lyrEl  = document.getElementById("lyrics-input");
      const fbEl   = document.getElementById("feedback-text");
      if (songEl && typeof st.song === "string") songEl.value = st.song;
      if (lyrEl && typeof st.lyrics === "string") lyrEl.value = st.lyrics;
      if (fbEl && typeof st.feedback === "string") fbEl.value = st.feedback;
    }

    function saveStudioState(silent=false) {
      try {
        const st = readStudioStateFromUI();
        localStorage.setItem(LS_KEY, JSON.stringify(st));
        if (!silent) setStudioStatus("保存しました");
      } catch (e) {
        console.warn(e);
        if (!silent) setStudioStatus("保存に失敗（localStorage不可）");
      }
    }

    function restoreStudioState(silent=false) {
      try {
        const raw = localStorage.getItem(LS_KEY);
        if (!raw) { if (!silent) setStudioStatus("保存データなし"); return; }
        const st = JSON.parse(raw);
        writeStudioStateToUI(st);
        if (!silent) setStudioStatus("復元しました");
      } catch (e) {
        console.warn(e);
        if (!silent) setStudioStatus("復元に失敗");
      }
    }

    function clearStudioState() {
      try { localStorage.removeItem(LS_KEY); } catch (e) {}
      const songEl = document.getElementById("song-title");
      const lyrEl  = document.getElementById("lyrics-input");
      const fbEl   = document.getElementById("feedback-text");
      if (songEl) songEl.value = "";
      if (lyrEl) lyrEl.value = "";
      if (fbEl) fbEl.value = "";
      setStudioStatus("クリアしました");
    }

    function applyTemplateFromSelect() {
      const sel = document.getElementById("template-select");
      const key = sel ? sel.value : "";
      if (!key) return;
      const t = TEMPLATES[key];
      if (!t) return;
      const songEl = document.getElementById("song-title");
      const lyrEl  = document.getElementById("lyrics-input");
      if (songEl) songEl.value = t.title;
      if (lyrEl)  lyrEl.value = t.lyrics;
      saveStudioState(true);
      setStudioStatus("テンプレ適用");
    }

    // =========================
    // Export helpers
    // =========================
    function setStatus(msg) {
      const el = document.getElementById("export-status");
      if (!el) return;
      el.textContent = msg || "";
      if (msg) setTimeout(() => { el.textContent = ""; }, 2200);
    }
    function getSongTitleSafe() {
      const t = (document.getElementById("song-title")?.value || "").trim();
      return t ? t.replace(/[\\\/:*?"<>|]/g, "_") : "singkana";
    }
    function fmt2(n){ return String(n).padStart(2,"0"); }
    function secToSrtTime(sec){
      const h = Math.floor(sec / 3600);
      const m = Math.floor((sec % 3600) / 60);
      const s = Math.floor(sec % 60);
      const ms = Math.floor((sec - Math.floor(sec)) * 1000);
      return `${fmt2(h)}:${fmt2(m)}:${fmt2(s)},${String(ms).padStart(3,"0")}`;
    }
    function buildKanaOnlyText() {
      if (!window.currentConvertedLines.length) return "";
      return window.currentConvertedLines.map(x => (x.kana || "").trim()).filter(Boolean).join("\n");
    }
    function buildEnKanaText() {
      if (!window.currentConvertedLines.length) return "";
      return window.currentConvertedLines.map(x => {
        const en = (x.en || "").trim();
        const ka = (x.kana || "").trim();
        const no = x.lineNo ? `#${x.lineNo}` : "";
        return `${no} ${en}\n${ka}`.trim();
      }).join("\n\n");
    }
    async function copyTextToClipboard(text) {
      if (!text) { setStatus("コピーする内容がありません"); return; }
      try {
        await navigator.clipboard.writeText(text);
        setStatus("コピーしました");
      } catch (e) {
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        setStatus("コピーしました");
      }
    }
    function downloadBlob(filename, content, mime) {
      const blob = new Blob([content], { type: mime || "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
    function copyKanaOnly(){ copyTextToClipboard(buildKanaOnlyText()); }
    function copyEnKana(){ copyTextToClipboard(buildEnKanaText()); }
    function downloadTxt(){
      const text = buildEnKanaText();
      if (!text) { setStatus("出力がありません"); return; }
      downloadBlob(`${getSongTitleSafe()}_singkana.txt`, text + "\n", "text/plain;charset=utf-8");
      setStatus("TXTを保存しました");
    }
    function downloadSrt(){
      if (!window.currentConvertedLines.length) { setStatus("出力がありません"); return; }
      const dur = 2.2;
      let t = 0;
      let idx = 1;
      const srt = window.currentConvertedLines.map(line => {
        const text = (line.kana || line.en || "").trim();
        const start = secToSrtTime(t);
        const end = secToSrtTime(t + dur);
        t += dur;
        return `${idx++}\n${start} --> ${end}\n${text}\n`;
      }).join("\n");
      downloadBlob(`${getSongTitleSafe()}_singkana.srt`, srt, "text/plain;charset=utf-8");
      setStatus("SRT(簡易)を保存しました");
    }

    // =========================
    // Highlight / Speak
    // =========================
    function setActiveBlock(block) {
      if (currentActiveBlock && currentActiveBlock !== block) currentActiveBlock.classList.remove("active");
      currentActiveBlock = block;
      if (block) block.classList.add("active");
    }
    function scrollActiveIntoView() {
      const chk = document.getElementById("auto-scroll");
      if (chk && !chk.checked) return;
      if (currentActiveBlock) currentActiveBlock.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    
    // ハッシュリンク（#terms, #privacy, #faq）の処理
    function showHashSection() {
      const hash = window.location.hash;
      if (hash === "#terms" || hash === "#privacy" || hash === "#faq") {
        const section = document.querySelector(hash);
        if (section) {
          // #terms と #privacy は hidden クラスを持つ
          if (hash === "#terms" || hash === "#privacy") {
            section.classList.remove("hidden");
          }
          section.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    }
    
    // ページ読み込み時とハッシュ変更時に実行
    showHashSection();
    window.addEventListener("hashchange", showHashSection);
    
    function speakKana(text) {
      if (!text || !text.trim()) return;
      if (!("speechSynthesis" in window)) return;
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(text);
      const voices = window.speechSynthesis.getVoices();
      const jpVoice = voices.find(v => v.lang && v.lang.toLowerCase().startsWith("ja"));
      if (jpVoice) utter.voice = jpVoice;
      window.speechSynthesis.speak(utter);
    }
    function setActiveIndex(i){
      if (!window.currentConvertedLines.length) return;
      window.activeIndex = Math.max(0, Math.min(i, window.currentConvertedLines.length - 1));
      const target = document.querySelector(`.result-block[data-line-no="${window.currentConvertedLines[window.activeIndex].lineNo}"]`);
      if (target) {
        setActiveBlock(target);
        const line = window.currentConvertedLines[window.activeIndex];
        const speakText = (line.kana && line.kana.trim()) ? line.kana : (line.en || "");
        speakKana(speakText);
        scrollActiveIntoView();
      }
    }
    function nextLine(){ if (window.currentConvertedLines.length) setActiveIndex((window.activeIndex < 0 ? 0 : window.activeIndex + 1)); }
    function prevLine(){ if (window.currentConvertedLines.length) setActiveIndex((window.activeIndex < 0 ? 0 : window.activeIndex - 1)); }

    // =========================
    // Display Layer
    // =========================
    function __getDisplayMode(){
      const el = document.getElementById("displayMode");
      return el ? el.value : "basic";
    }
    function _renderDisplayPlainText(coreText, mode){
      if (!coreText) return "";

      let t = String(coreText);
      t = t.replace(/\[.*?\]/g, "");
      t = t.replace(/\(.*?\)/g, "");
      t = t.replace(/[|\/]/g, "");
      // 区切り記号を統一（カンマを「｜」に置換）
      t = t.replace(/[,，]/g, "｜");

      if (mode === "precise") {
        return t.trim();
      }

      if (mode === "basic") {
        t = t.replace(/\s+/g, " ").trim();
        t = t.replace(/([ぁ-んァ-ヶ一-龠々〆ヵヶ])\s+([ぁ-んァ-ヶ一-龠々〆ヵヶ])/g, "$1$2");
        t = t.replace(/\s+([、。！？])/g, "$1");
        t = t.replace(/([、。！？])\s+/g, "$1");
        t = t.replace(/ー{2,}/g, "ー");
        t = t.replace(/っ\s+([ぁ-んァ-ヶA-Za-z])/g, "っ$1");
        t = t.replace(/\s{2,}/g, " ");
        return t.trim();
      }

      t = t.replace(/\s+/g, " ");
      t = t.replace(/([、。！？])\s*/g, "$1 ");
      t = t.replace(/([ぁ-ん]{10,})/g, (m) => {
        const chunks = [];
        for (let i = 0; i < m.length; i += 5) chunks.push(m.slice(i, i + 5));
        return chunks.join(" ");
      });
      t = t.replace(/\s{2,}/g, " ");
      return t.trim();
    }

    function renderDisplay(coreText, mode){
      if (!coreText) return "";
      const t = String(coreText);

      // HTML（差分ハイライトやタグ）が混ざるケースでは、属性を壊さないよう text node のみ加工
      if (t.includes("<")) {
        const tpl = document.createElement("template");
        tpl.innerHTML = t;
        const walker = document.createTreeWalker(tpl.content, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
          node.nodeValue = _renderDisplayPlainText(node.nodeValue, mode);
        }
        return tpl.innerHTML;
      }

      return _renderDisplayPlainText(t, mode);
    }

    function __displayModeChangeHandler(){
      if (!window.currentConvertedLines.length) return;
      const mode = __getDisplayMode();
      
      // モード切替時に結果が変わることを視覚的に示す（軽いアニメーション）
      const textDivs = document.querySelectorAll(".result-ka");
      textDivs.forEach((textDiv, i) => {
        // フェードアウト
        textDiv.style.opacity = "0.3";
        textDiv.style.transition = "opacity 0.15s ease";
        
        setTimeout(() => {
          const line = window.currentConvertedLines[i];
          if (textDiv && line) {
            // 比較UIの場合は差分ハイライトを適用
            const block = textDiv.closest(".rounded-lg, .rounded-xl");
            const isSingkana = block && block.classList.contains("border-singkana-400");
            
            if (isSingkana && line.standard) {
              // SingKANA版: 差分ハイライトを適用
              let highlighted = highlightDifferences(line.standard, line.singkana || "");
              if (isPro()) {
                highlighted = addBreathMarks(highlighted);
              }
              textDiv.innerHTML = renderDisplay(highlighted, mode);
            } else {
              // Standard版または通常表示
              textDiv.textContent = renderDisplay(line.kana || line.singkana || line.standard || "", mode);
            }
            
            // フェードイン
            textDiv.style.opacity = "1";
          }
        }, 100);
      });
      
      // モードバッジを更新（SingKANA側のブロックのみ）
      document.querySelectorAll(".border-singkana-400").forEach((block) => {
        const labelDiv = block.querySelector(".flex.items-center.gap-1.5");
        if (labelDiv) {
          // 既存のバッジを削除（ラベルテキスト以外のspan要素）
          const badges = labelDiv.querySelectorAll("span.inline-flex.items-center");
          badges.forEach(badge => badge.remove());
          
          // 新しいバッジを追加
          const badge = document.createElement("span");
          if (mode === "precise") {
            badge.className = "inline-flex items-center gap-0.5 px-1 py-0.5 rounded-full bg-purple-500/15 border border-purple-400/25 text-[8px] font-medium text-purple-200/80";
            badge.innerHTML = "🟪<span class=\"hidden md:inline\"> 日本語歌唱最適化</span>";
          } else if (mode === "natural") {
            badge.className = "inline-flex items-center gap-0.5 px-1 py-0.5 rounded-full bg-green-500/15 border border-green-400/25 text-[8px] font-medium text-green-200/80";
            badge.innerHTML = "🟩<span class=\"hidden md:inline\"> 英語リズム保持</span>";
          } else {
            badge.className = "inline-flex items-center gap-0.5 px-1 py-0.5 rounded-full bg-singkana-500/10 border border-singkana-400/20 text-[8px] font-medium text-singkana-200/70";
            badge.innerHTML = "🎤<span class=\"hidden md:inline\"> 歌唱向け</span>";
          }
          labelDiv.appendChild(badge);
          
          // 見出しテキストを更新
          const labelText = labelDiv.querySelector("span.text-\\[10px\\], span.text-singkana-100");
          if (labelText) {
            let newLabel, newShortLabel;
            if (mode === "precise") {
              newLabel = "日本語として歌えるカタカナ（最適）";
              newShortLabel = "日本語として歌える";
            } else if (mode === "natural") {
              newLabel = "英語っぽく歌えるカタカナ";
              newShortLabel = "英語っぽく歌える";
            } else {
              newLabel = "読むためのカタカナ";
              newShortLabel = "読むためのカタカナ";
            }
            labelText.innerHTML = `<span class="hidden md:inline">${newLabel}</span><span class="md:hidden">${newShortLabel}</span>`;
          }
        }
      });
    }

    // =========================
    // Convert (クライアントサイド一発変換 + 2段比較表示)
    // =========================
    function convertLyrics() {
      const errorBanner = document.getElementById("error-banner");
      const resultPanel = document.getElementById("result-panel");
      const lyrics = document.getElementById("lyrics-input").value || "";

      if (errorBanner) {
        errorBanner.style.display = "none";
        errorBanner.textContent = "";
      }

      if (!lyrics.trim()) {
        if (resultPanel) {
          resultPanel.innerHTML = "<p style='font-size:12px;color:#cbd5f5;'>歌詞を入力してください。</p>";
          setResultPlaceholderState();
        }
        return;
      }

      // SingKanaCoreが読み込まれているか確認
      if (!window.SingKanaCore || !window.SingKanaCore.convertLyrics) {
        console.error("[convertLyrics] SingKanaCore is not loaded");
        if (errorBanner) {
          errorBanner.textContent = "変換エンジンが読み込まれていません。ページを再読み込みしてください。";
          errorBanner.style.display = "block";
        }
        if (resultPanel) {
          resultPanel.innerHTML = "<p style='font-size:12px;color:#ff6b6b;'>変換エンジンが読み込まれていません。ページを再読み込みしてください。</p>";
          setResultPlaceholderState();
        }
        return;
      }

      let lines;
      try {
        // クライアントサイドで即座に変換（一発変換）
        lines = window.SingKanaCore.convertLyrics(lyrics);
        console.log("[convertLyrics] Converted lines:", lines);

        if (!lines || !lines.length) {
          window.currentConvertedLines = [];
          window.activeIndex = -1;
          if (resultPanel) {
            resultPanel.innerHTML = "<p style='font-size:12px;color:#cbd5f5;'>有効な行がありませんでした。</p>";
            setResultPlaceholderState();
          }
          saveStudioState(true);
          return;
        }
      } catch (error) {
        console.error("[convertLyrics] Error:", error);
        if (errorBanner) {
          errorBanner.textContent = `変換エラー: ${error.message}`;
          errorBanner.style.display = "block";
        }
        if (resultPanel) {
          resultPanel.innerHTML = `<p style='font-size:12px;color:#ff6b6b;'>変換エラーが発生しました: ${error.message}</p>`;
          setResultPlaceholderState();
        }
        return;
      }

      // 変換成功: 結果を表示
      // Standard変換（最適化なし）をクライアントサイドで生成
      const linesWithComparison = lines.map(line => {
        const standard = convertToStandardKana(line.en || "");
        return {
          en: line.en || "",
          standard: standard,
          singkana: line.kana || "",
          lineNo: line.lineNo || 0
        };
      });

      window.currentConvertedLines = linesWithComparison;
      window.activeIndex = -1;

      // 2段比較表示を構築
      const frag = document.createDocumentFragment();
      
      // デフォルト表示: Pro結果のみ（比較は折りたたみ）
      linesWithComparison.forEach((line, i) => {
        const lineContainer = document.createElement("div");
        lineContainer.className = "mb-3 md:mb-4";

        // 英語原文（スマホで非表示 or 小さく）
        const enDiv = document.createElement("div");
        enDiv.className = "hidden md:block text-xs text-slate-400 mb-2";
        enDiv.textContent = line.en || "";
        lineContainer.appendChild(enDiv);

        // SingKANA（最適化あり）- メイン表示
        const singkanaBlock = createComparisonBlock(
          "singkana",
          (() => {
            const mode = __getDisplayMode();
            if (mode === "precise") return "日本語として歌えるカタカナ（最適）";
            if (mode === "natural") return "英語っぽく歌えるカタカナ";
            return "読むためのカタカナ";
          })(),
          line.singkana || "",
          i,
          "singkana",
          line.standard || "" // Standard版と比較してハイライト
        );
        lineContainer.appendChild(singkanaBlock);

        // 比較トグル（Standard版を折りたたみ）
        const compareToggle = document.createElement("div");
        compareToggle.className = "mt-2";
        const toggleBtn = document.createElement("button");
        toggleBtn.className = "text-[10px] text-slate-400 hover:text-slate-300 transition flex items-center gap-1";
        toggleBtn.innerHTML = `<span>▼</span> <span>一般的なカタカナと比較する（歌いにくさの原因を見る）</span>`;
        
        const standardContainer = document.createElement("div");
        standardContainer.className = "hidden mt-2";
        const standardBlock = createComparisonBlock(
          "standard",
          "一般的なカタカナ（歌いやすさ最適化なし）",
          line.standard || "",
          i,
          "standard",
          null
        );
        standardContainer.appendChild(standardBlock);
        
        toggleBtn.onclick = () => {
          const isHidden = standardContainer.classList.contains("hidden");
          if (isHidden) {
            standardContainer.classList.remove("hidden");
            toggleBtn.innerHTML = `<span>▲</span> <span>一般的なカタカナを非表示</span>`;
          } else {
            standardContainer.classList.add("hidden");
            toggleBtn.innerHTML = `<span>▼</span> <span>一般的なカタカナと比較する（歌いにくさの原因を見る）</span>`;
          }
        };
        
        compareToggle.appendChild(toggleBtn);
        compareToggle.appendChild(standardContainer);
        lineContainer.appendChild(compareToggle);

        frag.appendChild(lineContainer);
      });

      // Pro誘導ボタン（比較UIの直下に配置）
      if (!isPro()) {
        const proCta = document.createElement("div");
        proCta.className = "mt-4 p-4 rounded-xl bg-gradient-to-r from-singkana-500/20 to-fuchsia-500/20 border border-singkana-400/40";
        proCta.innerHTML = `
          <div class="flex flex-col md:flex-row items-center justify-between gap-3">
            <div>
              <p class="text-sm font-semibold text-singkana-100 mb-1">この品質で変換し続ける</p>
              <p class="text-xs text-slate-300">Proで無制限変換・精密（日本語歌唱最適）・Singability（β）</p>
            </div>
            <a href="#pricing" class="inline-flex items-center justify-center gap-2 rounded-full bg-gradient-to-r from-singkana-500 to-fuchsia-500 px-6 py-2.5 text-sm font-semibold text-white shadow-glow hover:brightness-110 transition whitespace-nowrap">
              <span>Proを開始</span>
              <span class="text-xs">▶</span>
            </a>
          </div>
        `;
        frag.appendChild(proCta);
      }

      resultPanel.innerHTML = "";
      resultPanel.appendChild(frag);
      setResultPlaceholderState();

      setActiveIndex(0);
      saveStudioState(true);
    }


    // Standard変換（最適化なし）: クライアントサイド実装
    // 「機械的」「物足りない」「歌えない」を意図的に作る
    // WORD_OVERRIDESなし、フェイク発音なし、語尾ルールなし、ボーカルスタイルなし、伸ばしなし
    function convertToStandardKana(text) {
      if (!text || !text.trim()) return "";
      
      // 基本的な正規化のみ（アポストロフィ削除など）
      let line = text;
      line = line.replace(/[’'`´]/g, "");
      line = line.replace(/[:：]/g, " ");
      
      if (!line.trim()) return "";
      
      const words = line.split(/\s+/);
      const kanaWords = [];
      
      for (const raw of words) {
        if (!raw) continue;
        
        // 記号の処理
        const leadingPuncMatch = raw.match(/^[^A-Za-z0-9]+/);
        const trailingPuncMatch = raw.match(/[^A-Za-z0-9]+$/);
        const leadingPunc = leadingPuncMatch ? leadingPuncMatch[0] : "";
        const trailingPunc = trailingPuncMatch ? trailingPuncMatch[0] : "";
        
        const core = raw
          .replace(/^[^A-Za-z0-9]+/, "")
          .replace(/[^A-Za-z0-9]+$/, "");
        
        if (!core) {
          kanaWords.push(leadingPunc + trailingPunc);
          continue;
        }
        
        // 機械的なローマ字→かな変換（最適化一切なし）
        const kanaCore = romanToKanaStandard(core);
        kanaWords.push(leadingPunc + kanaCore + trailingPunc);
      }
      
      let kana = kanaWords.join(" ");
      
      // カタカナに統一（最適化なし、スペースはそのまま）
      kana = toKatakanaStandard(kana);
      
      return kana;
    }
    
    // 機械的なローマ字→かな変換（最適化一切なし）
    // 目的: 「物足りない」「歌えない」変換を作る
    function romanToKanaStandard(word) {
      if (!word) return "";
      
      let s = word.toLowerCase();
      
      // パターンマッチ一切なし（ph→ふ、sh→しなども使わない）
      // 文字単位の機械的な変換のみ
      const charMap = {
        a: "ア", e: "エ", i: "イ", o: "オ", u: "ウ",
        y: "イ",
        b: "ブ", c: "ク", d: "ド", f: "フ", g: "グ",
        h: "ハ", j: "ジ", k: "ク", l: "ル", m: "ム",
        n: "ン", p: "プ", q: "ク", r: "ル", s: "ス",
        t: "ト", v: "ヴ", w: "ウ", x: "クス", z: "ズ"
      };
      
      let result = [];
      for (let i = 0; i < s.length; i++) {
        const ch = s[i];
        if (charMap[ch]) {
          result.push(charMap[ch]);
        } else if (/[0-9]/.test(ch)) {
          result.push(ch);
        }
        // その他の文字は無視（機械的）
      }
      
      // スペースは入れない（単語ごとに区切るだけ）
      return result.join("");
    }
    
    // ひらがな→カタカナ変換（最適化なし）
    function toKatakanaStandard(str) {
      if (!str) return "";
      let result = str.replace(/[ぁ-ん]/g, function (ch) {
        return String.fromCharCode(ch.charCodeAt(0) + 0x60);
      });
      result = result.replace(/ゔ/g, "ヴ");
      return result;
    }
    
    // 差分ハイライト: Standard版とSingKANA版の違いを強調（本当に変わった部分だけ）
    function highlightDifferences(standard, singkana) {
      if (!standard || !singkana) {
        return escapeHtml(singkana || "");
      }

      // 単語単位で分割（スペース区切り）
      const standardWords = standard.split(/\s+/).filter(Boolean);
      const singkanaWords = singkana.split(/\s+/).filter(Boolean);
      
      // 単語単位で比較（本当に変わった部分だけをハイライト）
      const result = [];
      let sIdx = 0;
      let kIdx = 0;
      
      while (sIdx < standardWords.length || kIdx < singkanaWords.length) {
        if (sIdx < standardWords.length && kIdx < singkanaWords.length && 
            standardWords[sIdx] === singkanaWords[kIdx]) {
          // 一致する単語: 通常表示（色を付けない）
          result.push(escapeHtml(singkanaWords[kIdx]));
          sIdx++;
          kIdx++;
        } else {
          // 異なる単語: SingKANA側をハイライト（薄い背景のみ）
          if (kIdx < singkanaWords.length) {
            // 変更された部分だけを薄い背景で強調（色は控えめに）
            result.push(`<span class="bg-singkana-500/20 text-singkana-100 px-0.5 rounded">${escapeHtml(singkanaWords[kIdx])}</span>`);
            kIdx++;
          }
          // Standard側の異なる単語はスキップ
          if (sIdx < standardWords.length) {
            sIdx++;
          }
        }
        
        // スペースを追加（最後の単語以外）
        if (kIdx < singkanaWords.length || sIdx < standardWords.length) {
          result.push(" ");
        }
      }
      
      return result.join("");
    }
    
    // HTMLエスケープ
    function escapeHtml(text) {
      const div = document.createElement("div");
      div.textContent = text;
      return div.innerHTML;
    }
    
    // 比較ブロック（Standard/SingKANA）を作成
    function createComparisonBlock(type, label, text, lineIndex, mode, compareText) {
      const block = document.createElement("div");
      // SingKANA側は背景を少し暗くして主従を作る（Standardとの差を明度で取る）
      // Standard側は「安定させる」（背景・枠・装飾を削る）
      // スマホ最適化: パディング圧縮（p-4 → p-2.5 md:p-4）
      block.className = `rounded-lg md:rounded-xl border ${type === "singkana" ? "border-singkana-400/40 bg-slate-950/90 shadow-glow" : "border-slate-700/30 bg-transparent"} p-2.5 md:p-4`;

      // ヘッダー（ラベル + コピーボタン + 文字数）
      // スマホ最適化: マージン圧縮（mb-2 → mb-1.5 md:mb-2）
      const header = document.createElement("div");
      header.className = "flex items-center justify-between mb-1.5 md:mb-2 flex-wrap gap-1.5";
      
      const labelDiv = document.createElement("div");
      labelDiv.className = "flex items-center gap-1.5 flex-wrap";
      
      // ラベル（モードに応じて動的に変更）
      const labelText = document.createElement("span");
      labelText.className = `text-[10px] md:text-xs font-semibold ${type === "singkana" ? "text-singkana-100" : "text-slate-300"}`;
      
      // スマホでラベルを短縮（モードに応じて）
      let shortLabel;
      if (type === "singkana") {
        const mode = __getDisplayMode();
        if (mode === "precise") {
          shortLabel = "日本語として歌える";
        } else if (mode === "natural") {
          shortLabel = "英語っぽく歌える";
        } else {
          shortLabel = "読むためのカタカナ";
        }
      } else {
        shortLabel = "一般的なカタカナ";
      }
      
      labelText.textContent = shortLabel;
      labelText.innerHTML = `<span class="hidden md:inline">${label}</span><span class="md:hidden">${shortLabel}</span>`;
      labelDiv.appendChild(labelText);
      
      // SingKANA側にモードバッジを追加
      if (type === "singkana") {
        const mode = __getDisplayMode();
        const badge = document.createElement("span");
        
        // モードに応じたバッジを表示
        if (mode === "precise") {
          // 精密モード：日本語歌唱最適化バッジ
          badge.className = "inline-flex items-center gap-0.5 px-1 py-0.5 rounded-full bg-purple-500/15 border border-purple-400/25 text-[8px] font-medium text-purple-200/80";
          badge.innerHTML = "🟪<span class=\"hidden md:inline\"> 日本語歌唱最適化</span>";
        } else if (mode === "natural") {
          // ナチュラルモード：英語リズム保持バッジ
          badge.className = "inline-flex items-center gap-0.5 px-1 py-0.5 rounded-full bg-green-500/15 border border-green-400/25 text-[8px] font-medium text-green-200/80";
          badge.innerHTML = "🟩<span class=\"hidden md:inline\"> 英語リズム保持</span>";
        } else {
          // ベーシックモード：読む用バッジ
          badge.className = "inline-flex items-center gap-0.5 px-1 py-0.5 rounded-full bg-singkana-500/10 border border-singkana-400/20 text-[8px] font-medium text-singkana-200/70";
          badge.innerHTML = "🎤<span class=\"hidden md:inline\"> 歌唱向け</span>";
        }
        
        labelDiv.appendChild(badge);
      }
      
      header.appendChild(labelDiv);

      const actions = document.createElement("div");
      actions.className = "flex items-center gap-1.5 md:gap-2";
      
      // 文字数（スマホで小さく）
      const charCount = document.createElement("span");
      charCount.className = "text-[9px] md:text-[10px] text-slate-400";
      const textLength = (text || "").replace(/\s/g, "").length;
      charCount.textContent = `${textLength}文字`;
      actions.appendChild(charCount);

      // コピーボタン（スマホで小さく）
      const copyBtn = document.createElement("button");
      copyBtn.className = "inline-flex items-center gap-0.5 md:gap-1 px-1.5 md:px-2 py-0.5 md:py-1 rounded text-[9px] md:text-[10px] font-medium text-slate-300 hover:text-slate-100 bg-slate-800/50 hover:bg-slate-700/50 transition";
      copyBtn.innerHTML = `<span>📋</span><span class="hidden md:inline">Copy</span>`;
      copyBtn.onclick = (e) => {
        e.stopPropagation();
        navigator.clipboard.writeText(text || "").then(() => {
          copyBtn.innerHTML = "✓";
          setTimeout(() => {
            copyBtn.innerHTML = `<span>📋</span><span class="hidden md:inline">Copy</span>`;
          }, 1000);
        });
      };
      actions.appendChild(copyBtn);

      header.appendChild(actions);
      block.appendChild(header);

      // 変換結果テキスト（差分ハイライト付き）
      // スマホ最適化: フォントサイズ圧縮（text-sm → text-xs md:text-sm）
      // 行間を広げる（歌唱用テキストは「口に出すもの」なので読みやすく）
      const textDiv = document.createElement("div");
      textDiv.className = "result-ka text-xs md:text-sm text-slate-100 leading-loose md:leading-loose whitespace-pre-wrap";
      
      if (type === "singkana" && compareText) {
        // SingKANA版: 差分ハイライトを適用
        let highlighted = highlightDifferences(compareText, text);
        
        // Pro側だけブロック境界（息継ぎ位置）を表示（色ではなく記号で）
        if (isPro()) {
          // 息継ぎ位置に「｜」セパレータを挿入（色ではなく記号で区切りを表現）
          highlighted = addBreathMarks(highlighted);
        }
        
        textDiv.innerHTML = renderDisplay(highlighted, __getDisplayMode());
        
        // Pro側だけ「Singability（β）」を表示（仮実装）
        if (isPro()) {
          const scoreDiv = document.createElement("div");
          scoreDiv.className = "mt-2 pt-2 border-t border-singkana-400/20";
          scoreDiv.innerHTML = `
            <div class="flex items-center gap-2 text-[10px] text-singkana-200">
              <span class="font-semibold">Singability（β）:</span>
              <span class="text-singkana-100 font-bold">86/100</span>
              <span class="text-slate-400 ml-1">（息継ぎ・母音安定・連結自然さ）</span>
              <span class="text-slate-500 text-[9px] ml-1" title="β：現在は簡易推定">[β]</span>
            </div>
          `;
          textDiv.appendChild(scoreDiv);
        }
      } else {
        // Standard版: 通常表示（文字色は普通、背景・枠・装飾を削る）
        textDiv.textContent = renderDisplay(text || "", __getDisplayMode());
        textDiv.className += " text-slate-300";  // Standard版は安定した文字色
      }
      
      block.appendChild(textDiv);

      return block;
    }

    // =========================
    // ブロック境界（息継ぎ位置）の追加（Pro側のみ）
    // =========================
    function addBreathMarks(text) {
      if (!text) return text;
      
      // HTMLタグを一時的に保護
      const tagPlaceholders = [];
      let tagIndex = 0;
      let processed = text.replace(/<[^>]+>/g, (match) => {
        const placeholder = `__TAG_${tagIndex}__`;
        tagPlaceholders[tagIndex] = match;
        tagIndex++;
        return placeholder;
      });
      
      // 単語単位で分割（スペース区切り）
      const words = processed.split(/(\s+)/);
      const result = [];
      let wordCount = 0;
      
      for (let i = 0; i < words.length; i++) {
        const word = words[i];
        
        // タグプレースホルダーはそのまま
        if (word.startsWith('__TAG_')) {
          result.push(word);
          continue;
        }
        
        // スペースはそのまま
        if (/^\s+$/.test(word)) {
          result.push(word);
          continue;
        }
        
        // 単語をカウント
        wordCount++;
        
        // 3-4単語ごとに息継ぎ位置を挿入（自然な区切り）
        if (wordCount > 0 && (wordCount % 3 === 0 || wordCount % 4 === 0)) {
          result.push(word);
          // 軽いセパレータ「｜」を追加（色ではなく記号で、薄い色）
          result.push(' <span class="text-slate-500/30 text-xs mx-0.5">｜</span> ');
        } else {
          result.push(word);
        }
      }
      
      // タグプレースホルダーを元に戻す
      let final = result.join('');
      for (let i = 0; i < tagPlaceholders.length; i++) {
        final = final.replace(`__TAG_${i}__`, tagPlaceholders[i]);
      }
      
      return final;
    }

    // =========================
    // 例文挿入（1クリックで価値を踏ませる）
    // =========================
    function insertExample(type) {
      const lyricsInput = document.getElementById("lyrics-input");
      if (!lyricsInput) return;
      
      const examples = {
        fast: "Put your heart on the line, we'll be flying tonight",
        consonant: "I want you to know that I'm still here",
        vowel: "Fly me to the moon, let me play among the stars"
      };
      
      const example = examples[type] || examples.fast;
      
      // 既にテキストがある場合は確認
      if (lyricsInput.value.trim()) {
        if (!confirm("現在の入力内容を置き換えますか？")) {
          return;
        }
      }
      
      lyricsInput.value = example;
      lyricsInput.focus();
      
      // 自動変換（オプション）
      // convertLyrics();
    }

    // =========================
    // Feedback (NOTE: /api/feedback が未実装なら必ず失敗する)
    // → 失敗してもUXが壊れないようにする
    // =========================
    async function sendFeedback() {
      const textBox = document.getElementById("feedback-text");
      const status = document.getElementById("feedback-status");
      const text = (textBox.value || "").trim();
      status.textContent = "";

      if (!text) { status.textContent = "フィードバック内容を入力してください。"; return; }

      const title = document.getElementById("song-title").value || "";
      const meta = { song: title, client_side: true, engine_version: "js-core-v1.9" };

      try {
        const res = await fetch("/api/feedback", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ text, meta }),
        });

        const data = await res.json().catch(() => ({ ok: false }));
        if (data.ok) {
          status.textContent = "フィードバックありがとうございました。";
          textBox.value = "";
          saveStudioState(true);
        } else {
          status.textContent = "送信に失敗しました（API未接続の可能性）。";
        }
      } catch (e) {
        console.error(e);
        status.textContent = "送信に失敗しました（ネットワーク/API未接続）。";
      }
    }

    // =========================
    // 先行登録モーダル
    // =========================
    function openWaitlistModal() {
      const modal = document.getElementById("waitlist-modal");
      if (modal) {
        modal.classList.remove("hidden");
        document.body.style.overflow = "hidden"; // スクロール無効化
      }
    }

    function closeWaitlistModal() {
      const modal = document.getElementById("waitlist-modal");
      if (modal) {
        modal.classList.add("hidden");
        document.body.style.overflow = ""; // スクロール有効化
      }
    }

    async function submitWaitlist(event) {
      event.preventDefault();
      const emailInput = document.getElementById("waitlist-email");
      const agreeCheckbox = document.getElementById("waitlist-agree");
      const submitBtn = document.getElementById("waitlist-submit");
      const statusDiv = document.getElementById("waitlist-status");
      
      const email = (emailInput?.value || "").trim();
      
      if (!email) {
        statusDiv.textContent = "メールアドレスを入力してください。";
        statusDiv.className = "text-xs text-red-400 mt-2";
        return;
      }
      
      if (!agreeCheckbox?.checked) {
        statusDiv.textContent = "規約に同意してください。";
        statusDiv.className = "text-xs text-red-400 mt-2";
        return;
      }
      
      // 送信中
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "登録中...";
      }
      statusDiv.textContent = "";
      
      // 送信後2秒はdisable（連打防止）
      let disableTimeout = null;
      let disableDuration = 2000; // 基本2秒
      
      try {
        const res = await fetch("/api/waitlist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email })
        });
        
        // HTTPステータスコードをチェック
        if (!res.ok) {
          // エラーレスポンスをパース
          let errorMessage = "登録に失敗しました。しばらくしてから再度お試しください。";
          let errorCode = null;
          try {
            const errorData = await res.json();
            if (errorData.message) {
              errorMessage = errorData.message;
            }
            if (errorData.code) {
              errorCode = errorData.code;
            }
          } catch (e) {
            // JSONパースに失敗した場合はデフォルトメッセージ
          }
          
          statusDiv.textContent = errorMessage;
          statusDiv.className = "text-xs text-red-400 mt-2";
          
          // 429エラーの場合は10秒disable
          if (res.status === 429 || errorCode === "rate_limited") {
            disableDuration = 10000;
          }
          
          // disable期間を設定
          if (submitBtn) {
            disableTimeout = setTimeout(() => {
              if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = "先行利用に登録する";
              }
            }, disableDuration);
          }
          return;
        }
        
        // 成功レスポンスをパース
        const data = await res.json().catch(() => ({ ok: false, message: "レスポンスの解析に失敗しました。" }));
        
        if (data.ok) {
          // 成功（登録済みも含む）
          const isAlreadyRegistered = data.already_registered === true;
          statusDiv.textContent = data.message || "登録完了しました！";
          statusDiv.className = "text-xs text-green-400 mt-2";
          
          // フォームをリセット
          if (emailInput) emailInput.value = "";
          if (agreeCheckbox) agreeCheckbox.checked = false;
          
          // 成功メッセージとSNSフォローボタンを表示
          const successMessage = document.getElementById("waitlist-success-message");
          const snsSection = document.getElementById("waitlist-sns-section");
          if (successMessage) {
            successMessage.classList.remove("hidden");
          }
          if (snsSection) {
            snsSection.classList.remove("hidden");
          }
          
          // フォームを非表示
          const form = document.querySelector("#waitlist-modal form");
          if (form) {
            form.classList.add("hidden");
          }
          
          // 5秒後にモーダルを閉じる（SNSボタンを見せる時間を確保）
          setTimeout(() => {
            closeWaitlistModal();
            // モーダルを閉じる際に状態をリセット
            if (successMessage) successMessage.classList.add("hidden");
            if (snsSection) snsSection.classList.add("hidden");
            if (form) form.classList.remove("hidden");
            statusDiv.textContent = "";
          }, 5000);
        } else {
          // エラー
          statusDiv.textContent = data.message || "登録に失敗しました。";
          statusDiv.className = "text-xs text-red-400 mt-2";
          
          // disable期間を設定
          if (submitBtn) {
            disableTimeout = setTimeout(() => {
              if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = "先行利用に登録する";
              }
            }, disableDuration);
          }
        }
      } catch (e) {
        console.error("Waitlist registration error:", e);
        statusDiv.textContent = "登録に失敗しました。しばらくしてから再度お試しください。";
        statusDiv.className = "text-xs text-red-400 mt-2";
        
        // disable期間を設定
        if (submitBtn) {
          disableTimeout = setTimeout(() => {
            if (submitBtn) {
              submitBtn.disabled = false;
              submitBtn.textContent = "先行利用に登録する";
            }
          }, disableDuration);
        }
      } finally {
        // タイムアウトが設定されていない場合のみ即座に有効化
        if (!disableTimeout && submitBtn) {
          setTimeout(() => {
            if (submitBtn) {
              submitBtn.disabled = false;
              submitBtn.textContent = "先行利用に登録する";
            }
          }, disableDuration);
        }
      }
    }
