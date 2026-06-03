# petlife-api 設計メモ

FastAPI 在庫API + HTMX 在庫管理画面 + ダッシュボード。Railway デプロイ済み。

> 学習用の詳細な解説（なぜそうするのか、ハマった経緯、用語解説など）は
> `../学習メモ.md` に集約されています。ここはプロジェクト固有の本質情報のみ。

---

## ゴール

petlife-api を「API + 画面 一体型」のポートフォリオに育てる。
**既存の petlife-streamlit（別リポ）との互換性（JSON API URL）は壊さない**。

---

## ファイル構成

```
petlife-api/
├── main.py                    アプリ初期化のみ（CORS, static, include_router）
├── templating.py              Jinja2Templates の共通インスタンス
├── store.py                   データ層（_df + 取得/更新/追加/削除/集計）
├── routers/
│   ├── __init__.py
│   ├── pages.py               画面HTML（/ , /inventory , /new）
│   ├── stock_ui.py            HTMX 用 /ui/*（行編集・削除・新規POST）
│   └── stock_api.py           JSON API /stock/* と /health（streamlit互換）
├── stock.csv                  在庫マスタ（教育用 = メモリ操作のみで CSV は無傷）
├── requirements.txt           jinja2, python-multipart を含む
├── Procfile                   Railway 用
├── static/
│   ├── style.css              全画面共通CSS
│   └── dashboard.js           Chart.js 初期化（純JS、テンプレート記法ゼロ）
└── templates/
    ├── base.html              共通レイアウト
    ├── dashboard.html         トップページ（KPI + グラフ）
    ├── inventory.html         在庫一覧画面（HTMX）
    ├── new.html               新規登録フォーム
    ├── _rows.html             検索結果（全行を返す部分テンプレート）
    ├── _row.html              1行ぶんの <tr>（HTMX 単行差し替え / OOB swap で使い回し）
    ├── _qty_edit_cell.html    在庫数の編集モードセル
    └── _modal.html            詳細モーダル（全フィールド編集フォーム）
```

### モジュール分割の方針

- **main.py**：`FastAPI()` の生成、CORS、static の mount、`include_router` のみ。エンドポイント本体は持たない
- **store.py**：`_df` と全ヘルパー（取得/更新/追加/削除/絞り込み/ダッシュボード集計）。`_df` を再代入する関数は内部で `global _df` を宣言。ルーターは `import store` 経由で関数を呼ぶ（`from store import _df` はしない＝再代入後にズレるため）
- **templating.py**：`Jinja2Templates` の単一インスタンス。main と routers の両方から共通参照（main に置くと循環import）
- **routers/pages.py**：完全なHTMLページを返す画面ルート
- **routers/stock_ui.py**：HTMX 用（部分HTMLかリダイレクトのみ返す）
- **routers/stock_api.py**：JSON API（petlife-streamlit から呼ばれるので URL・レスポンス形は変えない）

---

## エンドポイント一覧

### HTML / HTMX 用（`/ui/*` と画面ルート）

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/` | ダッシュボード（KPI 5枚 + Chart.js 棒グラフ2本） |
| GET | `/inventory` | 在庫一覧画面（旧 `/`） |
| GET | `/new` | 新規登録フォーム画面 |
| GET | `/ui/rows` | 検索結果の部分HTML（HTMX 差し替え用） |
| GET | `/ui/stock/{sku}/edit_qty` | 通常セル → 編集セル差し替え |
| PUT | `/ui/stock/{sku}/qty` | 在庫数更新 + 行全体 `<tr>` 返却 |
| GET | `/ui/stock/{sku}/detail` | 詳細モーダルHTML（モーダル本体を返す） |
| PUT | `/ui/stock/{sku}/full` | 全フィールド更新 + OOB swap で `<tr>` 返却 |
| POST | `/ui/stock` | 新規登録 → `/inventory` に PRG リダイレクト |
| DELETE | `/ui/stock/{sku}` | 行削除 + 空HTML返却（フェードアウト） |

### JSON API（`/stock/*`、petlife-streamlit 互換）

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/stock` | 全在庫JSON |
| GET | `/stock/{sku}` | 1件取得 |
| PUT | `/stock/{sku}` | 在庫数更新（JSON） |
| GET | `/health` | ヘルスチェック |

---

## 重要な設計判断

### 1. URL 名前空間の分離

- `/ui/*` = HTML / HTMX 用（フォーム submit や部分HTML応答）
- `/stock/*` = JSON API（petlife-streamlit 互換）

→ デバッグしやすさ重視。同じ URL に複数メソッド/コンテンツタイプを乗せない。

### 2. 「メモリ上の `_df`」設計（教育用）

- `stock.csv` は起動時に1回だけ `load_df()` で読み込まれ、以降は `_df` を直接操作
- 削除・更新・追加は **メモリ上だけ** で完結（CSV は無傷）
- uvicorn 再起動で「巻き戻る」

これは意図的な設計：練習中に「全部消した、データ作り直し…」が起きない安心感を優先。
PostgreSQL 移行のタイミングで本物の永続化に切り替える予定。

### 3. 物理削除のまま進めている理由

業務システムでは論理削除が標準だが、petlife-api は今は商品マスタのみで履歴データがない。
業務直結機能（案B）で履歴データを作るタイミングで論理削除に切り替える方が、ストーリーが自然。

### 4. 「サーバーが返す HTML と hx-target は鏡合わせ」

| サーバーが返す中身 | hx-target | hx-swap |
|---|---|---|
| `<td>...</td>` だけ | `this` | `outerHTML` |
| `<tr>...</tr>` 行全体 | `closest tr` | `outerHTML` |

要発注フラグが在庫数連動で変わるため、「行全体を返す」設計を選択。

### 5. データアイランド方式（Python → JS のデータ受け渡し）

```html
<script id="category-data" type="application/json">{{ category_data | tojson }}</script>
<script src="/static/dashboard.js"></script>
```

→ `dashboard.js` はテンプレート記法ゼロの純JS。「`<script>` の中にテンプレート記法を書かない」を守る業界の解。

### 6. PRG パターン（POST-Redirect-GET）

新規登録の完了後は `RedirectResponse(url="/inventory", status_code=303)` でリダイレクト。
「戻る / 再読込」での二重 POST 送信を防ぐ。

### 7. 詳細モーダルと OOB swap（2026-05-26 追加）

- 一覧の「詳細」ボタン → `GET /ui/stock/{sku}/detail` で `_modal.html` を返し、`#modal-container` の innerHTML に差し込む（モーダル表示）
- モーダルの「保存」 → `PUT /ui/stock/{sku}/full` で全フィールド更新。レスポンスは `_row.html` を `oob=True` でレンダリング = `<tr id="row-XXX" hx-swap-oob="outerHTML">`
- HTMX は OOB swap タグをレスポンスから取り出して同 ID の要素を差し替え。残ったメイン応答は空 → `#modal-container` がクリアされて**モーダル自動で閉じる**
- = 1リクエストで「閉じる + 一覧行を最新化」が両立する設計
- カテゴリ・保管場所は `<select>` でマスタ既存値からのみ選択（フリー入力での表記揺れを防ぐ業務的判断）
- 閉じる動作は × ボタン / 背景クリック / ESC キー / キャンセルボタン の4経路。`closePetlifeModal()` を `_modal.html` 内 `<script>` で定義

### 8. SQLite 設計の方針（2026-06-02 追加）

**ファイル**: `db.py`（新設）。`stock.db` は起動時に CSV から自動 seed されるため、リポジトリには含めない（`.gitignore` で `*.db` を除外）。

**列名は英字**: DB 内部は英字（`sku_code` / `name` / `category_id` 等）。`store.py` で dict 変換するときに日本語キー（`SKUコード` / `商品名` 等）に戻すので、テンプレート・API レスポンス・petlife-streamlit との互換性は崩れない。

**要発注フラグは物理列にしない**: `SELECT *, (qty < reorder_point) AS 要発注 FROM stock` のように取得時に計算する。発注点や在庫数を変えただけで連動して値が変わるので、不整合が起きない。pandas 時代の `df["要発注"] = df["現在庫数"] < df["発注点"]` と同じ発想。

**接続管理**: `@contextmanager def get_conn()` で 1リクエスト 1接続。SQLite はファイルロックの仕様上、長期接続より都度接続のほうが安全。`with get_conn() as conn:` で抜けるとき自動 commit、例外時 rollback。

**FK 制約**: `PRAGMA foreign_keys = ON` を接続のたびに発行（SQLite はデフォルト OFF）。

**初回 seed の戦略**: `init_db()` で `CREATE TABLE IF NOT EXISTS` → 各テーブルが空なら CSV から流し込み。2回目以降は何もしない。`stock.csv` の1列目ヘッダーが「商品」（古い名残）になっているので、`DictReader` ではなく列順で読む。

**executescript と手動トランザクションは相性が悪い**: 最初 `isolation_level=None` で手動 `BEGIN` / `COMMIT` する設計にしたら、`executescript()` が内部で COMMIT を発行する仕様にぶつかって "no transaction is active" エラー。Python sqlite3 のデフォルト（DML 実行時に自動 BEGIN）に戻すと素直に動く。

**サンドボックスでは SQLite が動かない罠**: Linux サンドボックス経由で Windows マウントのファイルに SQLite が書き込もうとすると `disk I/O error`（FUSE マウントが SQLite の必要とする `fcntl` ロックをサポートしない）。動作確認は `/tmp` に DB ファイルを置いてやる。本番（Windows ローカル / Railway Linux）では普通に動く。

### 9. 部分テンプレートの粒度

- `_rows.html` = 全行
- `_row.html` = 1行（HTMX レスポンスでも使い回し）
- `_qty_edit_cell.html` = 1セル

ファイル名のアンダースコア + 単数形/複数形で粒度がひと目でわかる。

### ⚠️ Edit/Write ツールの罠（運用ノウハウ・2026-05-28 更新）
長い日本語コメント付きファイルを Edit/Write すると、Anthropic 側ツールのバグで：

- ~~ファイル末尾に null バイトが大量に混入する~~ → **2026-05-28 確認：解消されている**
- ファイル末尾が UTF-8 途中で切れる → **まだ残っている**（特に Edit を何度も重ねた長いファイルで発生）
- Read（Windows 側）と bash（Linux マウント側）で**同じファイルが違う状態に見える**ことがある
  - Read が 233 行に見えていても、ディスクは 225 行で切れている、というケースあり
  - bash で `>>` 追記すると、Windows 側の本物の末尾と二重化することがある

**運用ルール（2026-05-28 確定）：**
1. Edit/Write 直後は `wc -l` と `tail` で末尾を確認
2. 末尾補完するなら **Edit 一択**（bash `>>` 追記は同期ズレで二重化リスク）
3. Read ツールの表示を「正」として扱う（Windows ファイルシステム経由の方がディスク状態に近い）
4. bash と Read で行数がズレていたら警戒
5. **どうしても直らないときは bash の `cat << 'EOF'` でディスクに全文書き直し → cp で上書き**（2026-06-02 追加。Edit を重ねたあと bash 側だけ末尾切れたままになる現象の解決策）

---

## フィールド追加・修正時のチェックリスト

フィールド情報が複数ファイルに散らばっているため、フィールドを追加・修正・削除するときは以下を全部見ること。
（将来 Pydantic モデル化したら 1箇所で済むようになる予定）

### 必ず見るべき場所

| # | ファイル | 見るところ |
|---|---|---|
| 1 | `store.py` | `COLUMNS` / `EDITABLE_COLUMNS` / `load_df()` の型変換 / 派生フィールド計算（要発注など） |
| 2 | `routers/stock_ui.py` | `ui_create_stock` と `ui_update_full` の Form パラメータ + バリデーション |
| 3 | `routers/stock_api.py` | JSON API 互換（streamlit が見てる） |
| 4 | `templates/new.html` | 入力フォーム + 制約（`required` / `maxlength` / `pattern`） |
| 5 | `templates/_modal.html` | 入力フォーム + 制約 |
| 6 | `templates/_row.html` | 一覧表示列 |
| 7 | `templates/inventory.html` | colgroup の列幅と thead のラベル |
| 8 | `stock.csv` | 列順（1行目の列名と整合） |
| 9 | `static/style.css` | 必要に応じて |

### フィールド種類別の追加注意点

- **数値型**：`type="number" min="0"` 系の HTML 制約 + サーバ側 `int()` 変換 + 派生フィールドへの影響
- **選択式**：`store.get_xxx()` 候補取得関数 + 空 option `(未設定)` の有無 + マスタ外の値を許可するか
- **必須項目**：新規登録とモーダルで揃える（片方だけ必須は不整合）

---

## 残課題（次回以降）

| # | タスク | 工数 | メモ |
|---|---|---|---|
| ~~1~~ | ~~APIRouter リファクタリング~~ | ✅ 完了（2026-05-26） | store.py + templating.py + routers/{pages,stock_ui,stock_api}.py に分割 |
| ~~2~~ | ~~詳細モーダル（全フィールド編集）~~ | ✅ 完了（2026-05-26） | _modal.html + GET /detail + PUT /full + OOB swap で一覧と二段更新 |
| ~~3~~ | ~~新規登録の改善~~ | ✅ 完了（2026-05-26） | autocomplete=off + SKU/商品名 maxlength + pattern + 必須整理 + 備考 textarea |
| ~~4~~ | ~~カテゴリ・保管場所のマスタ化~~（コア完了） | ✅ 完了（2026-05-28） | id, name, sort_order, is_active の4列マスタ。stock.csv は ID 参照に移行。マスタ CRUD 画面（HTMX）追加。**UI 改善は #4.5 に分離**、マスタはメモリ運用（次の SQLite 移行で永続化） |
| ~~4.5~~ | ~~マスタ画面の UI 改善~~ | ✅ 完了（2026-06-01） | select 統一・action-cell 中央寄せ・長文省略（…+title）・sort_order 自動シフト方式・行追加方式（末尾「+追加」トリガー）・無効化ブロック（使用中なら 409 + alert）・他編集モード自動クローズ JS。詳細は下記「マスタ画面の UI 改善メモ」参照 |
| **4.6** | **SQLite 移行**（進行中） | 2〜3ユニット（うち1完了） | Railway 無料枠対策。stock / categories / locations を 1ファイル `stock.db` で管理。**2026-06-02：db.py + 初回 seed 完成**（上記「設計判断 #8」参照）。次ユニットで store.py を SQL ベースに書き換え。Pydantic モデル化はその次のユニット |
| 5 | 業務直結機能（CSV ダウンロード / 消費期限アラート / 入出荷登録） | 1〜2ユニット | 新しい `routers/exports.py` / `routers/transactions.py` として追加。**このタイミングで論理削除への切り替えを再検討** |
| 6 | README + スクショ更新 | 0.5〜1ユニット | 全機能完成後にまとめて |
| 7 | （将来）ログイン認証 + pytest による単体テスト | — | PetLife の bcrypt 経験を活用 |

### マスタ画面の UI 改善メモ（2026-05-28 user フィードバック → 2026-06-01 完了）

**実装サマリ（2026-06-01）**：
- 1, 2, 4：style.css に `.field select/textarea` 統一、`.action-cell` 中央寄せ＋`button+button` で 8px 余白、`.name-ellipsis` で長文…表示
- 3：`_add_master` / `_update_master` に「sort_order 重複時は N 以降を +1 シフト」ロジック追加。空欄時は max+1（末尾）
- 5：上の追加フォームを削除し、tbody 末尾に「+ {{ label }}を追加」トリガー行を常設。クリックで `_master_row_new.html` に差し替え、追加成功で `_master_rows.html`（全行）を返す
- 6：`ui_update_master` に「現在 active → 新値 inactive かつ 使用中なら 409」を追加。保存ボタンに `hx-on:htmx:response-error` で alert 表示
- 追加対策：複数同時編集を防ぐため、編集/追加トリガー押下時に `cancelOtherEdits()` で他の `.row-editing` をプログラム的にキャンセル

**新規/改修ファイル**：`templates/_master_rows.html`（全行）、`_master_add_trigger.html`、`_master_row_new.html`、`masters.html`（scriptブロック追加）、`_master_row.html` / `_master_row_edit.html`（hx-on 追加）、`routers/masters.py`（new-row / add-trigger エンドポイント追加、ロジックチェック追加）

**学んだこと（学習メモに転記候補）**：
- 「行間に依存があるならテーブル全行返す」「独立編集なら単行差し替え or OOB swap」の使い分け
- `hx-on:click` で HTMX リクエストと並行して JS を走らせる小ワザ
- `hx-on:htmx:response-error` で 4xx を alert に流す軽量エラー UI
- 「状態を URL とサーバに集中（B案）」と「クライアント JS で繕う（A案）」の設計トレードオフ

---

#### 当時の方針メモ（着手前、user フィードバック）

各項目に方針案（Claude の所感）も付記：

1. **select の見た目が他と統一できていない**
   - 新規登録 (`new.html`) / モーダル (`_modal.html`) の select が他のフォーム要素と比べて素のブラウザデフォルト
   - 対応：`static/style.css` で `select` に共通スタイル（input と同じ枠線・padding・font-size）
   - datalist だった頃は input 扱いで自動で統一されていた

2. **マスタ画面の「操作」ボタンが左寄りすぎ**
   - 現状：`.action-cell` 系のクラスを使っていない（既存 CSS と整合してない）
   - 対応：`_master_row.html` の操作セルに `class="action-cell"` を付ける + 必要なら `.action-cell` CSS で `padding` 調整

3. **sort_order の重複防止**
   - 現状：同じ番号を入れても通る → ドロップダウンの表示順が不安定
   - 方針候補：
     - (A) サーバ側で「重複したら以降を 1 ずつ後ろにずらす」自動シフト方式（業務系定番）
     - (B) 重複したらエラー返却して入力を弾く（シンプル）
   - 推奨：**(A) シフト方式**。user が「同じ数字の下は全部ずらす？」と書いてる通り、これが直感的

4. **カテゴリ名が長いとセルからはみ出して見切れる**
   - 対応：`white-space: nowrap; overflow: hidden; text-overflow: ellipsis;` で省略記号（…）に
   - もしくは、長い名前を許す方針なら `word-break: break-all;` で折り返し
   - 推奨：**省略記号 + title 属性で全文ホバー表示**。テーブルが崩れない

5. **「追加は上、編集は行内」の UX 分散がわかりにくい**
   - user 案：
     - (A) 編集も上のフォームに切り替える（編集時は上のフォームに既存値ロード）
     - (B) 新規追加も行追加方式にする（テーブル末尾に「+ 新規」行）
   - 推奨：**(B) 行追加方式**。テーブル一体で「これがマスタ全部」と直感的に分かる。HTMX も書きやすい

6. **「使用中マスタ」を無効化できてしまう → 在庫編集時に空欄になる問題**
   - 現状の挙動：
     - 削除はブロック（使用中なら ✕）
     - 無効化はブロックしない（無効にすると select から消える → モーダルで開くと空欄表示）
   - 業務的にどうあるべきか：
     - (A) 無効化もブロック（削除と同じ扱い）
     - (B) 無効化は許可、ただし**「使用中の在庫を含む select」では無効でも選択肢に残す**（モーダルだけ「無効」マーク付きで表示）
     - (C) 無効化は許可、空欄表示で OK（「無効化したら新しい登録には使えない」だけの意味）
   - 推奨：**(B) ハイブリッド**。「廃止予定だが既存在庫はまだ無効化前のラベルを保持」が業務的に最も自然。kintone のステータス管理に近い発想
   - ⚠️ 実装はやや重いので、**まず (A) シンプルブロック → 慣れたら (B) に拡張** でもよい

### 新規登録の改善案（残り）

2026-05-26 の作業で多くは消化済み。残り：

- 日付バリデーション強化（11111/11/11 等を弾く）
- 登録ボタンの「登録しますか？」「登録しました」フィードバック
- 登録後、一覧でその商品にフォーカスがあたる UI
