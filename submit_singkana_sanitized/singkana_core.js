// SingKANA JS Core v1.9
// 「歌ってみた」特化ボーカルスタイル版（Cモード）
// - 基本辞書(頻出100語＋歌寄せ調整 / すべてカタカナ統一)
// - 単語優先変換（句読点付きにも対応）
// - レリゴー補正（確実発火）
// - "ight" 系の順序修正
// - 行末ロングトーン強化
// - 英語行の最終出力をすべてカタカナに統一（ひらがな完全排除）
// - アポストロフィ（' / ’ / ` / ´）を全削除して TTS ノイズを除去
// - 「ゔ」はすべて「ヴ」に統一
// - 「:」「：」は歌詞出力から除去

(function (global) {
  "use strict";

  console.log("SingKANA JS Core v1.9 loaded");

  /* ================================
     0. NORMALIZE
  ================================== */
  function normalizeText(text) {
    if (!text) return "";
    return String(text)
      .replace(/\r\n/g, "\n")
      .replace(/\r/g, "\n")
      .replace(/\u3000/g, " ")
      .replace(/\t/g, " ")
      .replace(/ +/g, " ")
      .trim();
  }

  function hasLatin(str) {
    return /[A-Za-z]/.test(str);
  }

  function hasHangul(str) {
    return /[\uAC00-\uD7A3]/.test(str);
  }

  // 歌詞用：アポストロフィ／スマートクオートを整理
  function normalizeLyricLine(line) {
    if (!line) return "";
    let t = String(line);

    // いろんなアポストロフィ記号を普通の ' に寄せる
    t = t.replace(/[’‘‛‚`＇｀´]/g, "'");

    // ダブルクオート類もまとめておく
    t = t.replace(/[“”„]/g, '"');

    // rock 'n' roll → rock and roll
    t = t.replace(/\b'n\b/gi, " and ");

    // a'b → ab
    t = t.replace(/([A-Za-z])'([A-Za-z])/g, "$1$2");

    // 語末の ' （holdin' / lovin'' など）も削除
    t = t.replace(/([A-Za-z])'+\b/g, "$1");

    // 残っている ' は空白扱い
    t = t.replace(/'+/g, " ");

    // 全角コロンは半角に寄せておく（後段で削除）
    t = t.replace(/：/g, ":");

    return t;
  }

  // ひらがな → カタカナ
  function toKatakana(str) {
    if (!str) return "";
    return str.replace(/[ぁ-ん]/g, function (ch) {
      return String.fromCharCode(ch.charCodeAt(0) + 0x60);
    });
  }

  /* ================================
     1. BASIC WORD OVERRIDES (歌特化寄せ)
     ※ すべてカタカナで定義
  ================================== */
  const WORD_OVERRIDES = {
    // 代名詞・基本
    "you": "ユー",
    "your": "ユア",
    "i": "アイ",
    "me": "ミー",
    "my": "マイ",
    "we": "ウィー",
    "they": "ゼイ",
    "them": "ゼム",
    "it": "イット",

    // コア動詞・表現
    "let": "レット",
    "go": "ゴー",
    "come": "カム",
    "coming": "カミング",
    "run": "ラン",
    "running": "ランニング",
    "take": "テイク",
    "taking": "テイキング",
    "make": "メイク",
    "making": "メイキング",
    "want": "ウォント",
    "wanting": "ウォンティング",
    "need": "ニード",
    "needing": "ニーディング",
    "sing": "シング",
    "singing": "シンギング",
    "cry": "クライ",
    "crying": "クライング",
    "laugh": "ラフ",
    "laughing": "ラフィング",
    "hold": "ホールド",
    "holdin": "ホールディン",
    "holdin'": "ホールディン",

    // アポストロフィ系
    "cant": "キャント",

    // 感情・歌詞頻出
    "love": "ラヴ",
    "heart": "ハート",
    "feel": "フィール",
    "feels": "フィールズ",
    "feelings": "フィーリングス",
    "dream": "ドリーム",
    "dreaming": "ドリーミング",
    "desire": "デザイア",
    "fire": "ファイア",
    "higher": "ハイヤー",
    "fever": "フィーヴァー",

    // 時間・頻出ワード
    "again": "アゲイン",
    "more": "モォア",
    "anymore": "エニモァ",
    "forever": "フォーエヴァー",
    "never": "ネヴァー",
    "ever": "エヴァー",
    "today": "トゥデイ",
    "yesterday": "イエスタデイ",
    "tomorrow": "トゥモロー",

    // 場所・イメージ
    "night": "ナイト",
    "tonight": "トゥナイト",
    "light": "ライト",
    "bright": "ブライト",
    "right": "ライト",
    "wrong": "ロング",
    "strong": "ストロング",
    "storm": "ストーム",
    "door": "ドア",
    "before": "ビフォー",
    "after": "アフター",
    "inside": "インサイド",
    "outside": "アウツァイド",
    "world": "ワールド",
    "sky": "スカイ",
    "shine": "シャイン",
    "shining": "シャイニング",
    "gone": "ゴーン",
    "away": "アウェイ",

    // 接続・関係
    "with": "ウィズ",
    "without": "ウィザウト",
    "because": "ビコーズ",
    "just": "ジャスト",
    "trust": "トラスト",
    "believe": "ビリーヴ",

    // その他よく出る
    "dance": "ダンス",
    "dancing": "ダンシング",
    "call": "コール",
    "calling": "コーリング",

    // 宗教系など頻出ワード
    "lord": "ロード",
    "thanks": "サンクス",
    "praise": "プレイズ",
    "give": "ギヴ"
  };

  /* ================================
     2. PHRASE REPLACEMENTS
  ================================== */
  function postProcessKana(text) {
    let t = text;

    // レッ / レ ＋ イッ / ゴー → レリゴー
    t = t.replace(/レッ?\s*イッ?\s*ゴー/g, "レリゴー");

    return t;
  }

  /* ================================
     3. ボーカルスタイル C（歌特化）調整
  ================================== */
  function applyVocalStyleC(lineKana) {
    let t = lineKana;

    t = t.replace(/モア/g, "モォアァ");
    t = t.replace(/モォアー?/g, "モォアァ");
    t = t.replace(/ファイア/g, "ファイアァ");
    t = t.replace(/デザイア/g, "デザイアァ");
    t = t.replace(/タイム/g, "タイムゥ");
    t = t.replace(/ナイト/g, "ナイッ");
    t = t.replace(/ライト/g, "ライッ");

    // 行末ロングトーン強化（母音 or 母音＋ー）
    t = t.replace(/([アイウエオ])ー?\s*$/g, "$1ーー");

    return t;
  }

  /* ================================
     4. SIMPLE ROMAN → KANA (fallback)
     ※ ひらがなで構成し、最後にカタカナ化して返す
  ================================== */
  function romanToKana(word) {
    if (!word) return "";

    let s = word.toLowerCase();

    const patternMap = [
      ["tion", "しょん"],
      ["sion", "じょん"],
      ["ight", "あいと"],
      ["igh", "あい"],
      ["ph", "ふ"],
      ["sh", "し"],
      ["ch", "ち"],
      ["th", "す"],
      ["wh", "う"],
      ["ck", "く"],
      ["ng", "んぐ"],
      ["qu", "く"],
      ["oo", "うー"],
      ["ee", "いー"],
      ["ea", "いー"],
      ["ai", "えい"],
      ["ay", "えい"],
      ["ow", "あう"],
      ["ou", "あう"],
      ["er", "あー"],
      ["or", "おー"]
    ];
    patternMap.forEach(([from, to]) => {
      s = s.replace(new RegExp(from, "g"), to);
    });

    const charMap = {
      a: "あ",
      e: "え",
      i: "い",
      o: "お",
      u: "う",
      y: "い",
      b: "ぶ",
      c: "く",
      d: "ど",
      f: "ふ",
      g: "ぐ",
      h: "は",
      j: "じ",
      k: "く",
      l: "る",
      m: "む",
      n: "ん",
      p: "ぷ",
      q: "く",
      r: "る",
      s: "す",
      t: "と",
      v: "ゔ",
      w: "う",
      x: "くす",
      z: "ず"
    };

    let result = [];
    for (let i = 0; i < s.length; i++) {
      const ch = s[i];
      if (charMap[ch]) {
        result.push(charMap[ch]);
      } else if (/[0-9]/.test(ch)) {
        result.push(ch);
      }
    }

    let out = result.join("");

    // まずカタカナ化
    out = toKatakana(out);

    // 念のため「ゔ」が混じっていたら「ヴ」に
    out = out.replace(/ゔ/g, "ヴ");

    return out;
  }

  /* ================================
     5. KOREAN PLACEHOLDER
  ================================== */
  function koreanToKanaLine(line) {
    // v1.9 では未実装：将来 Hangul→かな変換を差し替える
    return line;
  }

  /* ================================
     6. MAIN: ENGLISH LINE → KANA LINE
  ================================== */
  function englishToKanaLine(line) {
    // 歌詞用にアポストロフィなどを正規化
    line = normalizeLyricLine(line);
    if (!line.trim()) return "";

    const words = line.split(/\s+/);
    const kanaWords = [];

    for (const raw of words) {
      if (!raw) continue;

      // 先頭・末尾の記号を拾う
      const leadingPuncMatch = raw.match(/^[^A-Za-z0-9]+/);
      const trailingPuncMatch = raw.match(/[^A-Za-z0-9]+$/);

      // 歌詞では ' / ’ はただの装飾とみなして捨てる
      const leadingPunc =
        (leadingPuncMatch ? leadingPuncMatch[0] : "").replace(/[’']/g, "");
      const trailingPunc =
        (trailingPuncMatch ? trailingPuncMatch[0] : "").replace(/[’']/g, "");

      const core = raw
        .replace(/^[^A-Za-z0-9]+/, "")
        .replace(/[^A-Za-z0-9]+$/, "");

      if (!core) {
        kanaWords.push(leadingPunc + trailingPunc);
        continue;
      }

      const lower = core.toLowerCase();

      let kanaCore;
      if (Object.prototype.hasOwnProperty.call(WORD_OVERRIDES, lower)) {
        kanaCore = WORD_OVERRIDES[lower];
      } else {
        kanaCore = romanToKana(core);
      }

      kanaWords.push(leadingPunc + kanaCore + trailingPunc);
    }

    let kana = kanaWords.join(" ");

    // 念のため ' 系の記号を完全除去
    kana = kana.replace(/[’‘'｀´]/g, "");

    // コロン系は全部消す（歌詞には不要）
    kana = kana.replace(/[:：]/g, " ");

    // フレーズ補正 & ボーカルスタイル
    kana = postProcessKana(kana);
    kana = applyVocalStyleC(kana);

    // 英語行の最終出力をカタカナに統一
    kana = toKatakana(kana);

    // 最終保険：ひらがな → カタカナ
    kana = kana.replace(/[ぁ-ん]/g, function (ch) {
      return String.fromCharCode(ch.charCodeAt(0) + 0x60);
    });

    // 「ゔ」が残っていたらすべて「ヴ」に
    kana = kana.replace(/ゔ/g, "ヴ");

    return kana;
  }

  /* ================================
     7. LYRICS 全体変換
  ================================== */
  function convertLyrics(text) {
    const norm = normalizeText(text);
    if (!norm) return [];

    const rawLines = norm.split("\n");
    const out = [];
    let lineNo = 0;

    for (const raw of rawLines) {
      const line = raw.replace(/\r/g, "").trimEnd();
      if (!line.trim()) continue;

      lineNo += 1;

      let kana;
      if (hasLatin(line)) {
        kana = englishToKanaLine(line);
      } else if (hasHangul(line)) {
        kana = koreanToKanaLine(line);
      } else {
        kana = line;
      }

      out.push({
        lineNo,
        en: line,
        kana
      });
    }

    return out;
  }

  global.SingKanaCore = {
    normalizeText,
    convertLyrics,
    englishToKanaLine
  };
})(window);
