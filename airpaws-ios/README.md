## AirPaws (Phase1 / MVP) iOS 実装一式

このフォルダは **AirPaws Phase1(MVP)** の SwiftUI 実装コード（App + WidgetExtension）を、Xcode プロジェクトへ取り込みやすい形でまとめたものです。

思想ロック v1.0 に従い、**説明しない / 競争させない / 誇示させない** を前提に、Widget は「表示だけ」、アプリは「タップで足跡→次回ロック画面に反映」を最小で実装します。

---

## 1. Xcode プロジェクト構成（作成手順）

Xcode で新規プロジェクトを作成します。

- **Product Name**: AirPaws
- **Interface**: SwiftUI
- **Language**: Swift
- **Bundle Identifier**: 例 `com.airpaws.app`（任意。ただし App Group は仕様固定）
- **Minimum iOS**: iOS 16 以上を推奨（WidgetKit + SwiftUI 前提）

続けて Widget Extension を追加します。

- `File > New > Target... > Widget Extension`
- **Include Configuration Intent**: OFF
- **Include Live Activity**: OFF

作成後、次のフォルダ構成になるようにこの `airpaws-ios/` 配下の Swift ファイルを Xcode に追加（ドラッグ＆ドロップ）し、**Target Membership** を設定します。

---

## 2. 追加する Swift ファイルと配置

このリポジトリ上の配置（参考）:

```
airpaws-ios/
  Shared/
    AppConstants.swift
    Models.swift
    SharedStore.swift
    Assets.swift
  AirPawsApp/
    AirPawsApp.swift
    HomeView.swift
    PawprintsOverlayView.swift
  AirPawsWidget/
    AirPawsWidget.swift
```

Xcode 上では以下のように設定してください（重要）。

- **Shared/**: すべて **Appターゲット + WidgetExtensionターゲット** の両方にチェック
- **AirPawsApp/**: **Appターゲットのみ**
- **AirPawsWidget/**: **WidgetExtensionターゲットのみ**

---

## 3. Capabilities 設定（必須）

### 3.1 App Groups

App と Widget の両方の Target で有効化します。

- `Signing & Capabilities` → `+ Capability` → `App Groups`
- **App Group**: `group.com.airpaws.app`

### 3.2 URL Scheme（仕様）

App ターゲットの `Info` に URL Types を追加します。

- **URL Schemes**: `airpaws`

Widget 側からは `airpaws://open` を設定して、タップでアプリが開きます。

---

## 4. Assets（最低限の命名）

Xcode の `Assets.xcassets` に以下の名前で画像を追加してください（未追加でもビルドは通りますが表示は空になります）。

- `bg_base_01`
- `pet_cat_orange_base` / `pet_cat_orange_blink` / `pet_cat_orange_surprise` / `pet_cat_orange_raincoat` / `pet_cat_orange_scarf`
- `atm_rain_01..03` / `atm_snow_01..03` / `atm_wind_01..03` / `atm_thunder_01..02` / `atm_sun_01..02`
- `pawprint_common_01`

---

## 5. 動作仕様（Phase1）

### 5.1 共有データ（AppGroup UserDefaults）

- `SharedState`: `selectedCharacterID`, `lens(cute/chic)`, `weather(clear/rain/snow/wind/thunder)`, `pawprints[]`, `catDisplayName?`, `showNameOnWidget`, `updatedAt`
- `PawprintStamp`: `id`, `x,y(0..1)`, `opacity`, `createdAt`
- `SharedStore`: load/save/defaultState

補足:

- `SharedStore` は日付の encode/decode に `iso8601` を使っています。**Widget 側も必ず同じ `SharedStore.swift` をターゲットに含めてください**（ズレると decode 失敗します）。

### 5.2 App（Home）

- 背景 + 猫を表示
- 猫（画面）タップで瞬間反応（blink）し、タップ位置に足跡生成 → **12秒でフェードアウト（表示のみ）**
- 生成した足跡は `SharedStore` に保存（**最新8個まで**）し、`WidgetCenter.reloadAllTimelines()` で反映
- Lens 切替（Cute/Chic）だけ UI に用意（設定画面は Phase1 では作らない）

### 5.3 Widget

- **Home**: `.systemSmall`（`bg_base_01 + pet + atm(天気差分フレーム)`）
- **Lock**: `.accessoryRectangular`（猫＋足跡＋空気、情報ほぼなし）
- ロック画面 Rectangular のみ、`showNameOnWidget == true` かつ `catDisplayName` 非空のとき、右下に極小で表示（opacity: cute=0.55 / chic=0.35）
- Widget は重い処理なし（表示のみ）
- Timeline: **30分刻みで3エントリ**

---

## 6. 動作確認手順（ロック画面追加含む）

### 6.1 App の動作

1. 実機（推奨）で App を起動
2. Home 画面の猫（画面）をタップ
3. 足跡が出て 12 秒で消えることを確認
4. 直後にウィジェット（Home/Lock）を確認し、足跡が反映されることを確認
5. `Cute/Chic` 切替でロック画面の名前表示 opacity が変わることを確認（名前表示をONにした場合）

### 6.2 ロック画面への追加（.accessoryRectangular）

1. iPhone のロック画面を長押し
2. `カスタマイズ` → `ロック画面` を選択
3. ウィジェット枠をタップ
4. 一覧から **AirPaws** を選び、**Rectangular** を追加
5. ロック画面に戻って表示を確認

---

## 7. 補足

- 天気（`weather`）は Phase1 では固定で OK。後で Open-Meteo（キー無し）に差し替え前提の設計だけ入っています。
- 共有/課金/ランキング/実績/フォローは Phase1 では実装しません（設計のみ）。

