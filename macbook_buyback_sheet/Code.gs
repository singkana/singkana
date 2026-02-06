/**
 * MacBook 出張買取（スプシ運用）ツール
 *
 * ねらい:
 * - スマホで「入力」シートに入力するだけで、見積レンジが自動更新される（onEdit）。
 * - ベース価格と減額は「設定」シートで編集可能（相場更新をスプシ側で吸収）。
 *
 * 注意:
 * - スマホアプリではカスタムメニューが表示されないことが多いので、onEditを主軸にする。
 * - 初期セットアップ（setup）はPCからApps Scriptエディタで1回実行推奨。
 */

// ===== シート名（固定） =====================================================
var SHEET_INPUT = "入力";
var SHEET_CONFIG = "設定";

// ===== 入力シート列定義（1-based） ===========================================
// 入力列（ユーザーが触る）
var COL_CREATED_AT = 1; // A: 自動
var COL_QUOTE_ID = 2;   // B: 自動
var COL_CUSTOMER = 3;   // C
var COL_PHONE = 4;      // D
var COL_FAMILY = 5;     // E: Air / Pro
var COL_YEAR = 6;       // F: 2017..2026
var COL_SIZE = 7;       // G: 13/14/15/16
var COL_CHIP = 8;       // H: Intel / M1 / M2 / M3 / M1 Pro...
var COL_RAM = 9;        // I: 8/16/32/64
var COL_SSD = 10;       // J: 256/512/1024/...
var COL_GRADE = 11;     // K: S/A/B/C/D
var COL_BATTERY = 12;   // L: OK / Service / Unknown
var COL_SCREEN = 13;    // M: OK / Damage / Unknown
var COL_KEYBOARD = 14;  // N: OK / Issue / Unknown
var COL_ACCESSORIES = 15;// O: Charger+Box / Charger / None
var COL_REPAIR = 16;    // P: None / Yes / Unknown
var COL_NOTES = 17;     // Q

// 計算結果列（スクリプトが更新）
var COL_BASE_LOW = 18;  // R
var COL_BASE_HIGH = 19; // S
var COL_DED_LOW = 20;   // T
var COL_DED_HIGH = 21;  // U
var COL_QUOTE_LOW = 22; // V
var COL_QUOTE_HIGH = 23;// W
var COL_STATUS = 24;    // X: New/Sent/Booked/Done
var COL_LAST_CALC_AT = 25; // Y
var COL_MESSAGE = 26;   // Z: お客様連絡文（コピペ用）

var INPUT_HEADER = [
  "作成日時",
  "見積ID",
  "お客様名",
  "電話",
  "機種",
  "年式",
  "画面(インチ)",
  "チップ",
  "メモリ(GB)",
  "SSD(GB)",
  "状態グレード",
  "バッテリー",
  "画面状態",
  "キーボード",
  "付属品",
  "修理歴/水没",
  "メモ",
  "ベース下限(円)",
  "ベース上限(円)",
  "減額下限(円)",
  "減額上限(円)",
  "見積下限(円)",
  "見積上限(円)",
  "ステータス",
  "最終計算",
  "連絡文（コピペ）"
];

// ===== 設定シートのテーブル定義 =============================================
// 「設定」シートの上部にBASE、下部にDEDUCTIONSを置く（ヘッダ行を含む）
var CONFIG_BASE_START_ROW = 2;      // 2行目から
var CONFIG_BASE_START_COL = 1;      // A列から
var CONFIG_BASE_HEADERS = [
  "種別", "年式", "画面", "チップ", "メモリ", "SSD",
  "ベース下限(円)", "ベース上限(円)", "メモ"
];

var CONFIG_DED_TITLE_ROW_GAP = 2; // BASEの後に空行+タイトル行を入れる
var CONFIG_DED_HEADERS = [
  "要素", "選択肢", "減額下限(円)", "減額上限(円)", "メモ"
];

function setupMacbookBuybackSheet() {
  var ss = SpreadsheetApp.getActive();
  var input = ss.getSheetByName(SHEET_INPUT) || ss.insertSheet(SHEET_INPUT);
  var config = ss.getSheetByName(SHEET_CONFIG) || ss.insertSheet(SHEET_CONFIG);

  // ---- 入力シート初期化 ----
  input.clear();
  input.getRange(1, 1, 1, INPUT_HEADER.length).setValues([INPUT_HEADER]);
  input.setFrozenRows(1);
  input.setColumnWidths(1, 26, 140);
  input.getRange(1, 1, 1, INPUT_HEADER.length).setFontWeight("bold");

  // ---- 設定シート初期化 ----
  config.clear();
  config.getRange(1, 1).setValue("BASE_PRICE（ベース価格テーブル）");
  config.getRange(1, 1).setFontWeight("bold");
  config.getRange(CONFIG_BASE_START_ROW, CONFIG_BASE_START_COL, 1, CONFIG_BASE_HEADERS.length)
    .setValues([CONFIG_BASE_HEADERS])
    .setFontWeight("bold");

  // デフォルトのベース価格（サンプル。実運用では相場に合わせて更新）
  var baseSample = [
    ["Air", 2020, 13, "M1", 8, 256, 45000, 65000, "サンプル"],
    ["Air", 2020, 13, "M1", 16, 512, 60000, 80000, "サンプル"],
    ["Pro", 2021, 14, "M1 Pro", 16, 512, 95000, 125000, "サンプル"],
    ["Pro", 2021, 16, "M1 Pro", 16, 512, 115000, 145000, "サンプル"],
    ["Pro", "*", "*", "Intel", "*", "*", 15000, 60000, "Intelは幅を広めに（要更新）"]
  ];
  config.getRange(CONFIG_BASE_START_ROW + 1, 1, baseSample.length, CONFIG_BASE_HEADERS.length).setValues(baseSample);

  // DEDUCTIONS セクション開始行
  var baseEndRow = CONFIG_BASE_START_ROW + 1 + baseSample.length;
  var dedTitleRow = baseEndRow + CONFIG_DED_TITLE_ROW_GAP;
  var dedHeaderRow = dedTitleRow + 1;

  config.getRange(dedTitleRow, 1).setValue("DEDUCTIONS（減額テーブル）");
  config.getRange(dedTitleRow, 1).setFontWeight("bold");
  config.getRange(dedHeaderRow, 1, 1, CONFIG_DED_HEADERS.length)
    .setValues([CONFIG_DED_HEADERS])
    .setFontWeight("bold");

  var dedSample = [
    ["grade", "S", 0, 0, ""],
    ["grade", "A", -5000, -8000, ""],
    ["grade", "B", -15000, -25000, ""],
    ["grade", "C", -30000, -45000, ""],
    ["grade", "D", -60000, -90000, ""],
    ["battery", "OK", 0, 0, ""],
    ["battery", "Service", -10000, -15000, "バッテリー修理推奨/劣化"],
    ["battery", "Unknown", -3000, -8000, "不明は保守的に"],
    ["screen", "OK", 0, 0, ""],
    ["screen", "Damage", -20000, -60000, "割れ/表示不良/強いムラ"],
    ["screen", "Unknown", -5000, -15000, ""],
    ["keyboard", "OK", 0, 0, ""],
    ["keyboard", "Issue", -8000, -15000, "キー欠け/反応不良等"],
    ["keyboard", "Unknown", -3000, -8000, ""],
    ["accessories", "Charger+Box", 0, 0, ""],
    ["accessories", "Charger", -1000, -3000, "箱なし"],
    ["accessories", "None", -3000, -7000, "充電器なし"],
    ["repair", "None", 0, 0, ""],
    ["repair", "Yes", -10000, -30000, "修理歴/水没/基板修理など"],
    ["repair", "Unknown", -5000, -15000, ""]
  ];
  config.getRange(dedHeaderRow + 1, 1, dedSample.length, CONFIG_DED_HEADERS.length).setValues(dedSample);

  // ---- データバリデーション（入力） ----
  // 入力の候補はスクリプト側で固定（簡易）。運用に合わせるなら設定シートから引く。
  setValidationList_(input, COL_FAMILY, ["Air", "Pro"]);
  setValidationList_(input, COL_SIZE, ["13", "14", "15", "16"]);
  setValidationList_(input, COL_CHIP, ["Intel", "M1", "M1 Pro", "M1 Max", "M2", "M2 Pro", "M2 Max", "M3", "M3 Pro", "M3 Max"]);
  setValidationList_(input, COL_RAM, ["8", "16", "32", "64"]);
  setValidationList_(input, COL_SSD, ["128", "256", "512", "1024", "2048", "4096"]);
  setValidationList_(input, COL_GRADE, ["S", "A", "B", "C", "D"]);
  setValidationList_(input, COL_BATTERY, ["OK", "Service", "Unknown"]);
  setValidationList_(input, COL_SCREEN, ["OK", "Damage", "Unknown"]);
  setValidationList_(input, COL_KEYBOARD, ["OK", "Issue", "Unknown"]);
  setValidationList_(input, COL_ACCESSORIES, ["Charger+Box", "Charger", "None"]);
  setValidationList_(input, COL_REPAIR, ["None", "Yes", "Unknown"]);
  setValidationList_(input, COL_STATUS, ["New", "Sent", "Booked", "Done"]);

  // 年式は数値入力を想定（入力補助として表示形式）
  input.getRange(2, COL_YEAR, input.getMaxRows() - 1, 1).setNumberFormat("0");

  // 見積欄は通貨っぽく
  input.getRange(2, COL_BASE_LOW, input.getMaxRows() - 1, 6).setNumberFormat("#,##0");

  // 連絡文を見やすく
  input.getRange(2, COL_MESSAGE, input.getMaxRows() - 1, 1).setWrap(true);

  // 説明（1行目右側）
  input.getRange(1, 28).setValue("メモ：入力(E〜P)を編集すると自動で見積更新");
  input.autoResizeColumn(28);
}

function setValidationList_(sheet, col, values) {
  var rule = SpreadsheetApp.newDataValidation()
    .requireValueInList(values, true)
    .setAllowInvalid(true)
    .build();
  sheet.getRange(2, col, sheet.getMaxRows() - 1, 1).setDataValidation(rule);
}

// ===== 自動計算トリガ（スマホ運用向け） =====================================
function onEdit(e) {
  try {
    if (!e || !e.range) return;
    var sheet = e.range.getSheet();
    if (sheet.getName() !== SHEET_INPUT) return;
    var row = e.range.getRow();
    if (row < 2) return; // header

    // 入力列（E〜Q）が更新されたら再計算
    var col = e.range.getColumn();
    var min = COL_FAMILY;
    var max = COL_NOTES;
    if (col < min || col > max) return;

    recalcRow_(sheet, row);
  } catch (err) {
    // simple trigger ではLoggerが見えにくいので、セルに痕跡を残す
    try {
      var r = e && e.range ? e.range.getRow() : 0;
      var sh = e && e.range ? e.range.getSheet() : null;
      if (sh && r >= 2) {
        sh.getRange(r, COL_LAST_CALC_AT).setValue("ERR: " + String(err));
      }
    } catch (_) {}
  }
}

function recalcRow_(inputSheet, row) {
  // created_at / quote_id の自動付与
  var createdAt = inputSheet.getRange(row, COL_CREATED_AT).getValue();
  if (!createdAt) {
    inputSheet.getRange(row, COL_CREATED_AT).setValue(new Date());
  }
  var qid = String(inputSheet.getRange(row, COL_QUOTE_ID).getValue() || "").trim();
  if (!qid) {
    qid = generateQuoteId_();
    inputSheet.getRange(row, COL_QUOTE_ID).setValue(qid);
  }

  var input = readInputRow_(inputSheet, row);

  // 入力が不足している場合はクリア
  if (!input.family || !input.year || !input.chip || !input.ram || !input.ssd) {
    writeCalc_(inputSheet, row, null);
    return;
  }

  var cfg = loadConfig_();
  var base = findBestBasePrice_(cfg.basePrices, input);
  if (!base) {
    // ベースが無い場合も計算欄は残す（気づきやすくする）
    writeCalc_(inputSheet, row, {
      baseLow: "",
      baseHigh: "",
      dedLow: "",
      dedHigh: "",
      quoteLow: "",
      quoteHigh: "",
      message: "ベース価格が未登録です（設定シートを更新してください）"
    });
    return;
  }

  var ded = calcDeductions_(cfg.deductions, input);

  var quoteLow = Math.max(0, toNumber_(base.low) + toNumber_(ded.low));
  var quoteHigh = Math.max(0, toNumber_(base.high) + toNumber_(ded.high));

  // 下限<=上限になるように整形（減額幅の入れ方で逆転するのを防ぐ）
  var lo = Math.min(quoteLow, quoteHigh);
  var hi = Math.max(quoteLow, quoteHigh);

  var msg = buildCustomerMessage_(qid, input, base, ded, lo, hi);

  writeCalc_(inputSheet, row, {
    baseLow: base.low,
    baseHigh: base.high,
    dedLow: ded.low,
    dedHigh: ded.high,
    quoteLow: lo,
    quoteHigh: hi,
    message: msg
  });
}

function readInputRow_(sheet, row) {
  var v = sheet.getRange(row, COL_CUSTOMER, 1, (COL_NOTES - COL_CUSTOMER + 1)).getValues()[0];
  // vは C..Q の配列
  return {
    customer: String(v[0] || "").trim(),
    phone: String(v[1] || "").trim(),
    family: String(v[2] || "").trim(),
    year: normalizeYear_(v[3]),
    size: normalizeMaybeNumber_(v[4]),
    chip: String(v[5] || "").trim(),
    ram: normalizeMaybeNumber_(v[6]),
    ssd: normalizeMaybeNumber_(v[7]),
    grade: String(v[8] || "").trim(),
    battery: String(v[9] || "").trim(),
    screen: String(v[10] || "").trim(),
    keyboard: String(v[11] || "").trim(),
    accessories: String(v[12] || "").trim(),
    repair: String(v[13] || "").trim(),
    notes: String(v[14] || "").trim()
  };
}

function normalizeYear_(val) {
  var n = toNumber_(val);
  if (!n) return "";
  if (n < 2000 || n > 2100) return "";
  return String(Math.round(n));
}

function normalizeMaybeNumber_(val) {
  var n = toNumber_(val);
  if (!n) return "";
  return String(Math.round(n));
}

function writeCalc_(sheet, row, calc) {
  var now = new Date();
  if (!calc) {
    sheet.getRange(row, COL_BASE_LOW, 1, 6).clearContent(); // R..W
    sheet.getRange(row, COL_LAST_CALC_AT).setValue(now);
    sheet.getRange(row, COL_MESSAGE).clearContent();
    return;
  }

  sheet.getRange(row, COL_BASE_LOW).setValue(calc.baseLow);
  sheet.getRange(row, COL_BASE_HIGH).setValue(calc.baseHigh);
  sheet.getRange(row, COL_DED_LOW).setValue(calc.dedLow);
  sheet.getRange(row, COL_DED_HIGH).setValue(calc.dedHigh);
  sheet.getRange(row, COL_QUOTE_LOW).setValue(calc.quoteLow);
  sheet.getRange(row, COL_QUOTE_HIGH).setValue(calc.quoteHigh);
  sheet.getRange(row, COL_LAST_CALC_AT).setValue(now);
  sheet.getRange(row, COL_MESSAGE).setValue(calc.message || "");
}

function loadConfig_() {
  var ss = SpreadsheetApp.getActive();
  var config = ss.getSheetByName(SHEET_CONFIG);
  if (!config) throw new Error("設定シートがありません。setupMacbookBuybackSheet を実行してください。");

  var basePrices = loadBasePrices_(config);
  var deductions = loadDeductions_(config);

  return { basePrices: basePrices, deductions: deductions };
}

function loadBasePrices_(configSheet) {
  // BASEタイトル(1行目) + ヘッダ(2行目) + データ(3行目〜) を想定
  var lastRow = configSheet.getLastRow();
  if (lastRow < CONFIG_BASE_START_ROW + 1) return [];

  // baseは「空行」か「DEDUCTIONS」タイトルに当たる行まで
  var dataStart = CONFIG_BASE_START_ROW + 1;
  var data = configSheet.getRange(dataStart, 1, lastRow - dataStart + 1, CONFIG_BASE_HEADERS.length).getValues();
  var rows = [];
  for (var i = 0; i < data.length; i++) {
    var r = data[i];
    var isEmpty = true;
    for (var k = 0; k < 6; k++) {
      if (String(r[k] || "").trim() !== "") { isEmpty = false; break; }
    }
    if (isEmpty) continue;

    // "DEDUCTIONS" のタイトル行は [ "DEDUCTIONS..." ] だけ入る想定なので弾く
    if (String(r[0] || "").toUpperCase().indexOf("DEDUCTIONS") >= 0) break;

    rows.push({
      family: String(r[0] || "").trim(),
      year: String(r[1] || "").trim(),
      size: String(r[2] || "").trim(),
      chip: String(r[3] || "").trim(),
      ram: String(r[4] || "").trim(),
      ssd: String(r[5] || "").trim(),
      low: toNumber_(r[6]),
      high: toNumber_(r[7]),
      note: String(r[8] || "").trim()
    });
  }
  return rows;
}

function loadDeductions_(configSheet) {
  // DEDUCTIONSの見出しを探す（シート内検索は重いので、下半分を走査）
  var lastRow = configSheet.getLastRow();
  if (lastRow < 1) return {};

  var values = configSheet.getRange(1, 1, lastRow, 5).getValues();
  var headerRow = -1;
  for (var i = 0; i < values.length; i++) {
    var a = String(values[i][0] || "").trim();
    var b = String(values[i][1] || "").trim();
    if (a === CONFIG_DED_HEADERS[0] && b === CONFIG_DED_HEADERS[1]) {
      headerRow = i + 1; // 1-based
      break;
    }
  }
  if (headerRow < 0) return {};

  var map = {};
  for (var r = headerRow + 1; r <= lastRow; r++) {
    var row = values[r - 1];
    var factor = String(row[0] || "").trim();
    var opt = String(row[1] || "").trim();
    if (!factor || !opt) continue;
    if (!map[factor]) map[factor] = {};
    map[factor][opt] = {
      low: toNumber_(row[2]),
      high: toNumber_(row[3]),
      note: String(row[4] || "").trim()
    };
  }
  return map;
}

function findBestBasePrice_(basePrices, input) {
  var best = null;
  var bestScore = -1;

  for (var i = 0; i < basePrices.length; i++) {
    var row = basePrices[i];
    var m = matchScore_(row, input);
    if (m < 0) continue;
    if (m > bestScore) {
      bestScore = m;
      best = row;
    }
  }
  return best;
}

function matchScore_(row, input) {
  // row側が "*" or 空 ならワイルドカード扱い
  var score = 0;
  var pairs = [
    ["family", input.family],
    ["year", input.year],
    ["size", input.size],
    ["chip", input.chip],
    ["ram", input.ram],
    ["ssd", input.ssd]
  ];

  for (var i = 0; i < pairs.length; i++) {
    var key = pairs[i][0];
    var want = String(pairs[i][1] || "").trim();
    var have = String(row[key] || "").trim();
    if (!have || have === "*") {
      continue;
    }
    if (!want) return -1;
    if (have !== want) return -1;
    score += 1;
  }

  // base_low/high が無効なら弾く
  if (!isFiniteNumber_(row.low) || !isFiniteNumber_(row.high)) return -1;
  return score;
}

function calcDeductions_(dedMap, input) {
  var sumLow = 0;
  var sumHigh = 0;

  var factors = [
    ["grade", input.grade],
    ["battery", input.battery],
    ["screen", input.screen],
    ["keyboard", input.keyboard],
    ["accessories", input.accessories],
    ["repair", input.repair]
  ];

  for (var i = 0; i < factors.length; i++) {
    var f = factors[i][0];
    var opt = String(factors[i][1] || "").trim();
    if (!opt) continue;
    var ent = dedMap[f] && dedMap[f][opt];
    if (!ent) continue;
    sumLow += toNumber_(ent.low);
    sumHigh += toNumber_(ent.high);
  }

  return { low: sumLow, high: sumHigh };
}

function buildCustomerMessage_(quoteId, input, base, ded, low, high) {
  var parts = [];
  parts.push("【MacBook 出張買取 見積】");
  parts.push("見積ID: " + quoteId);
  parts.push("機種: " + [input.family, input.year, (input.size ? input.size + "inch" : ""), input.chip, input.ram + "GB", input.ssd + "GB"].filter(Boolean).join(" / "));
  parts.push("概算: " + formatYen_(low) + " 〜 " + formatYen_(high));
  parts.push("");
  parts.push("※状態（外観/動作/バッテリー/画面）や付属品の確認後、最終金額が前後します。");
  parts.push("※アクティベーションロック解除・初期化が確認できない場合は買取不可になることがあります。");
  return parts.join("\n");
}

function formatYen_(n) {
  var x = toNumber_(n);
  var s = Math.round(x).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return s + "円";
}

function generateQuoteId_() {
  // 例: MBQ-20260205-8F3K2
  var tz = Session.getScriptTimeZone() || "Asia/Tokyo";
  var d = Utilities.formatDate(new Date(), tz, "yyyyMMdd");
  var rand = (Math.random().toString(36).toUpperCase().replace(/[^A-Z0-9]/g, "")).slice(0, 5);
  if (rand.length < 5) rand = (rand + "00000").slice(0, 5);
  return "MBQ-" + d + "-" + rand;
}

function toNumber_(v) {
  if (v === null || v === undefined || v === "") return 0;
  if (typeof v === "number") return v;
  var s = String(v).replace(/,/g, "").trim();
  var n = Number(s);
  return isFinite(n) ? n : 0;
}

function isFiniteNumber_(v) {
  return typeof v === "number" && isFinite(v);
}

