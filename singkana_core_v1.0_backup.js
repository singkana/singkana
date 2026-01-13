v1.3


// SingKANA JS Core v1.3
// 「歌ってみた」特化ボーカルスタイル版（Cモード）
// - 基本辞書(頻出100語＋歌寄せ調整)
// - 単語優先変換
// - フレーズ補正（レリゴー等）
// - 行末の母音を歌いやすく伸ばす（長音寄せ）

(function (global) {
  "use strict";

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

  /* ================================
     1. BASIC WORD OVERRIDES (歌特化寄せ)
     ※ lower case キーでマッチ
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
    "it": "イッ",

    // コア動詞・表現
    "let": "レッ",
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
    "tonight": "トゥナイッ",
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
    "calling": "コーリング"
  };

  /* ================================
     2. PHRASE REPLACEMENTS
     カタカナ化後に「歌っぽく」寄せる
  ================================== */
  function postProcessKana(text) {
    let t = text;

    // 代表フレーズ
    t = t.replace(/レ\s*イッ\s*ゴー/g, "レリゴー");
    t = t.replace(/アイ\s*ラヴ\s*ユー/g, "アイラブユー");
    t = t.replace(/ユー\s*エン\s*ダイ/g, "ユーエンダイ");
    t = t.replace(/キャント\s*ホール?ディッ?バッ/g, "キャントホーリッバッ");
    t = t.replace(/ヒア\s*アイ\s*(アム|ム)/g, "ヒアアイム");

    // 少し伸ばし系
    t = t.replace(/フォーエヴァー/g, "フォーエヴァー");
    t = t.replace(/エヴァー/g, "エヴァー");

    return t;
  }

  /* ================================
     3. ボーカルスタイル C（歌特化）調整
     - 行末の母音を軽く伸ばす
     - 一部の単語をさらに歌寄せ
  ================================== */
  function applyVocalStyleC(lineKana) {
    let t = lineKana;

    // 単語単位でさらに歌寄せ
    t = t.replace(/モア/g, "モォアァ");
    t = t.replace(/モォアー?/g, "モォアァ");
    t = t.replace(/ファイア/g, "ファイアァ");
    t = t.replace(/デザイア/g, "デザイアァ");
    t = t.replace(/タイム/g, "タイムゥ");
    t = t.replace(/ナイト/g, "ナイッ");
    t = t.replace(/ライト/g, "ライッ");

    // 行末の母音を少し伸ばす（歌の最後を意識）
    // ...アイ / イ / ア / オ / ウ で終わっていたら ー を付ける
    t = t.replace(/([アイウエオあいうえお])\s*$/g, "$1ー");

    return t;
  }

  /* ================================
     4. SIMPLE ROMAN → KANA (fallback)
     ※辞書にないもの用の簡易ルール
  ================================== */
  function romanToKana(word) {
    if (!word) return "";

    let s = word.toLowerCase();

    const patternMap = [
      ["tion", "しょん"],
      ["sion", "じょん"],
      ["igh", "あい"],
      ["ight", "あいと"],
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
      ["or", "おー"],
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
      z: "ず",
    };

    let result = [];
    for (let i = 0; i < s.length; i++) {
      const ch = s[i];
      if (charMap[ch]) {
        result.push(charMap[ch]);
      } else if (/[0-9]/.test(ch)) {
        result.push(ch);
      } else {
        result.push(ch);
      }
    }

    return result.join("");
  }

  /* ================================
     5. KOREAN PLACEHOLDER
  ================================== */
  function koreanToKanaLine(line) {
    // v1.3では未実装：将来 Hangul→かな変換をここに実装
    return line;
  }

  /* ================================
     6. MAIN: ENGLISH LINE → KANA LINE
  ================================== */
  function englishToKanaLine(line) {
    const words = line.split(/\s+/);
    const kanaWords = [];

    for (let w of words) {
      if (!w) continue;

      const raw = w;
      const lower = raw.toLowerCase();

      // 基本辞書優先
      if (Object.prototype.hasOwnProperty.call(WORD_OVERRIDES, lower)) {
        kanaWords.push(WORD_OVERRIDES[lower]);
      } else {
        kanaWords.push(romanToKana(raw));
      }
    }

    let kana = kanaWords.join(" ");

    // 歌っぽいフレーズ補正
    kana = postProcessKana(kana);
    // Cモードのボーカルスタイル適用
    kana = applyVocalStyleC(kana);

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

      let kana = line;
      if (hasLatin(line)) {
        kana = englishToKanaLine(line);
      } else if (hasHangul(line)) {
        kana = koreanToKanaLine(line);
      } else {
        // 日本語・その他はそのまま
        kana = line;
      }

      out.push({
        lineNo,
        en: line,
        kana,
      });
    }

    return out;
  }

  // 公開インターフェース
  global.SingKanaCore = {
    normalizeText,
    convertLyrics,
  };
})(window);




# PLACEHOLDER: singkana_core.js content will be inserted manually by the user.
