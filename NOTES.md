# petlife-api 「本命ルート適用」メモ

2026-05-22 セッションで、petlife-api 本体に HTMX 画面を生やしたときの所感メモ。
htmx-search で覚えたことを実プロジェクトに適用するフェーズ。

---

## ゴール

petlife-api を「API + 画面 一体型」に育てる。
既存の petlife-streamlit（別リポ）との互換性（JSON API URL）は壊さない。

## 変更内容

| 区分 | パス | 役割 | 状態 |
|---|---|---|---|
| HTML UI | `/` | 在庫一覧画面（HTMX） | **新規** |
| HTML UI | `/ui/rows` | HTMX用の部分HTML | **新規** |
| JSON API | `/health` | ヘルスチェック | `/` から移動 |
| JSON API | `/stock` | 全在庫JSON | **変更なし**（Streamlit互換） |
| JSON API | `/stock/{sku}` | 1件取得 / 在庫更新 | **変更なし**（Streamlit互換） |

## 実装した機能（ステップA〜C）

- **ステップA**: `base.html` + `index.html` + `_rows.html` で在庫一覧テーブル表示
- **ステップB**: 検索バー（カテゴリ select / キーワード input / 要発注 checkbox）+ `hx-trigger="input changed delay:300ms, change, submit"` でリアルタイム検索
- **ステップC**: 要発注の行を CSS で薄い赤色に強調表示（`tr.row-low td`）

## ファイル構成

```
petlife-api/
├── main.py              FastAPI + HTMX 統合
├── stock.csv            在庫マスタ（変更なし）
├── requirements.txt     jinja2 を追加
├── Procfile             変更なし
├── static/
│   └── style.css        ★ 新規・外出しした共通CSS
└── templates/
    ├── base.html        共通レイアウト（CSS は外出し済み）
    ├── index.html       在庫一覧画面（base.html を継承）
    └── _rows.html       検索結果の部分テンプレート（HTMX用）
```

---

## htmx-search との対応関係

| htmx-search | petlife-api | メモ |
|---|---|---|
| 社員データ（モジュール内リスト） | 在庫データ（CSV → pandas DataFrame） | データソースが本格的 |
| `filter_employees()` | `filter_stocks()` | 同じ発想（完全一致＋部分一致＋ブール） |
| 英語キー (`emp_no`, `name`) | 日本語キー (`SKUコード`, `商品名`) | テンプレートでは `s["SKUコード"]` |
| CSS は `base.html` 内インライン | CSS は `static/style.css` に外出し | ★ 今回の新スキル |
| JS インライン（モーダル） | なし | HTMX のみで完結 |
| `_results.html` | `_rows.html` | 名前を在庫向けに調整 |

---

## 今回の新習得

### 1. CSS の外出し + FastAPI の StaticFiles

main.py に1行追加するだけ：

```python
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
```

これで `/static/foo.css` というURLが `./static/foo.css` ファイルに対応する。
`base.html` 側は `<link rel="stylesheet" href="/static/style.css">` で読み込む。

**メリット**:
- ファイル分離で `<style>` ブロックの肥大化を回避
- ブラウザがCSSをキャッシュ → 2回目以降の読み込みが速い
- VSCode の CSS Language Service がフルで動く
- 複数ページで同じCSSを共有可能
- CLAUDE.md の学び「`<style>` の中にテンプレート記法を書かない」と同じ方向の改善

### 2. Jinja2 で日本語キーの辞書アクセス

stock.csv のキー名が日本語（`SKUコード`、`商品名` …）のため、ドット記法が使えない：

```jinja
{# NG: Python の属性アクセスは ASCII の識別子だけ扱える #}
{{ s.SKUコード }}

{# OK: 辞書アクセスの形ならキー名を問わない #}
{{ s["SKUコード"] }}
```

英語キーなら両方使えるが、日本語キーがあるなら **全部ブラケット記法に統一する** のが安全。

### 3. checkbox の HTMX 連携

```html
<input type="checkbox" id="low_only" name="low_only" value="true">
```

- チェック時だけ `?low_only=true` がクエリに付く
- 未チェック時は何も送られない（空文字も来ない）
- FastAPI 側で `low_only: bool = False` と書くと `"true"` を True に変換してくれる
- デフォルト値 `False` のおかげで「送られなかった = False」が自然に成立

### 4. パスの定石

```python
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "stock.csv"
templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
```

「実行中ファイルからの相対パス」を絶対パス化することで、どこから uvicorn を起動しても安定する。htmx-search でも同じパターンを使った。

---

## 残課題（次回以降）

- **README のスクショ更新**：「API + 画面 一体型」になった旨を反映
- **petlife-streamlit との役割整理**：HTMX 画面ができたので、Streamlit 版の位置づけを再検討（残す/廃止/役割限定）

---

# 2026-05-24 追記: ステップD（インライン編集）実装

## ゴール

在庫一覧の「現在庫数」セルをクリック → その場で input → Enter または blur → PUT で更新 → 行全体が差し替わる（要発注フラグの強調表示も連動）。CRUD の **U**（Update）を完成させる。

## 変更内容

| 区分 | パス | 役割 | 状態 |
|---|---|---|---|
| HTML UI | `GET /ui/stock/{sku}/edit_qty` | 通常セル → 編集セル（input）に差し替え | **新規** |
| HTML UI | `PUT /ui/stock/{sku}/qty` | 在庫数を更新して **行全体** (`<tr>`) を返す | **新規** |
| JSON API | `PUT /stock/{sku}` | JSON版（petlife-streamlit 互換） | **変更なし**（共通処理関数を呼ぶように内部整理のみ） |

ファイル変更：
- `main.py`: `from fastapi import Form` 追加、補助関数 `update_qty_in_df()` / `get_stock_or_404()` を切り出し、HTMX用2エンドポイントを追加
- `templates/_row.html`: **新設**。1行ぶんの `<tr>` を単独テンプレート化（HTMX レスポンスでも使い回す）
- `templates/_qty_edit_cell.html`: **新設**。編集モードのセル `<td><input ...></td>`
- `templates/_rows.html`: 1行ぶんを `{% include "_row.html" %}` に置き換え
- `static/style.css`: `.qty-cell`（通常時のホバーヒント） / `.qty-cell-editing`（編集中の input スタイル）を追加
- `requirements.txt`: `python-multipart` を追加

## 今回の新習得

### 1. 「サーバーが返す HTML と hx-target は鏡合わせ」原則

| サーバーが返す中身 | hx-target | hx-swap |
|---|---|---|
| `<td>...</td>` だけ | `this` | `outerHTML` |
| `<tr>...</tr>` 行全体 | `closest tr` | `outerHTML` |

今回は在庫数を変えると **要発注フラグ**（赤背景・フラグ列）も連動して変わるため、「行全体を返す」設計を選択。target も `closest tr` で行を狙う。**htmx-search の削除機能で使ったパターン (`hx-target="closest tr"`) と同じ発想**。

### 2. Form(...) と python-multipart の依存関係

FastAPI で `qty: int = Form(...)` のようにフォームデータを受け取るには、**追加ライブラリ `python-multipart` が必要**。FastAPI 本体には含まれていない。インストールせずに起動すると：

```
RuntimeError: Form data requires "python-multipart" to be installed.
You can install "python-multipart" with: pip install python-multipart
```

→ エラーメッセージに解決策が書いてある親切なタイプ。`pip install python-multipart` で解決。**Railway デプロイ用に requirements.txt にも追記必須**（忘れると本番で落ちる）。

HTMX が送ってくるのが `application/x-www-form-urlencoded` 形式なので、Python 側でパースするのに必要。JSON ボディなら不要。

### 3. hx-trigger の複数イベント + キー指定の構文

```html
hx-trigger="change, keydown[key=='Enter']"
```

- **複数イベントはカンマ + スペース区切り**（スペースだけだと「change という名前のイベントを keydown[enter] という修飾子で…」と誤解される）
- **キー指定の `[ ... ]` 内は JavaScript の条件式として評価される**。だから `keydown[enter]` ではなく `keydown[key=='Enter']`（イベントオブジェクトの `key` プロパティを文字列と比較）
- `change` だけでも実は動く（Enter を押すと input から離れる扱いで自動的に発火する）。ただ Enter で即送信を明示するなら両方書く方が親切。

### 4. CORS と「同一オリジン」の意味

ブラウザは「画面のドメイン」と「API のドメイン」が違うとデフォルトで止める（CORS）。
- 同一オリジン（同じドメイン:ポート）→ そのまま通る。許可表明は不要
- 別オリジン → サーバー側が `CORSMiddleware` で許可表明していないと止められる

今回追加した HTMX エンドポイントは画面と同じ petlife-api アプリ内なので **同一オリジン** → CORS の出番なし。既存の `allow_origins=["*"]` は petlife-streamlit（別オリジン）からの呼び出し用。

### 5. Number input のスピンボタンを消す CSS

業務系の表で number input の上下矢印は邪魔になりがち。

```css
input[type="number"] {
    -moz-appearance: textfield;
}
input[type="number"]::-webkit-outer-spin-button,
input[type="number"]::-webkit-inner-spin-button {
    -webkit-appearance: none;
    margin: 0;
}
```

Firefox 系と WebKit 系で書き方が違うので両方書く必要がある。

### 6. 部分テンプレートの「育て方」のコツ

`_rows.html` の中にあった1行ぶんの `<tr>` を `_row.html` に切り出した理由：**PUT レスポンスでも同じ「1行」を返したいから**。

部分テンプレートは「**HTMX のどの差し替え単位で返したいか**」を考えて切り出す粒度を決めるとよい。今回は：
- 全行を返す `→ _rows.html`
- 1行だけ返す `→ _row.html`（新設）
- 1セルだけ返す `→ _qty_edit_cell.html`（新設）

「ファイル名のアンダースコア + 単数形/複数形」で粒度がひと目でわかる。

## 「ハマったエラー」の振り返り

### `python-multipart` 未インストール
- エラー文の **一番下** に解決策まで書いてあった（CLAUDE.md 既存学び「エラー対処の3ステップ」がそのまま使える）
- requirements.txt への追記を忘れると Railway デプロイ時に同じエラーが本番で出る

### キー名 `'SKU'` vs `'SKUコード'`
- Jinja2 は存在しないキーをエラーにせず空文字を返す性質（CLAUDE.md 既存学び）のため、`{{ s['SKU'] }}` と書いても **動作はする**（URL が `/ui/stock//qty` になって 404 になるが、エディタは止めない）
- **動かして初めて気付く罠**。日本語キーのプロジェクトでは「キー名を文字単位で見直すクセ」が安全

---

# 2026-05-24 追記2: ダッシュボード化（案A、KPI + Chart.js）

## ゴール

トップページに「見せ場」を作る。CRUD のチュートリアルに見えがちな状態から、「**データの整形・分析・レポート化**」の名乗りと直結する画面を追加。

## 変更内容

| 区分 | パス | 役割 | 状態 |
|---|---|---|---|
| HTML UI | `/` | **ダッシュボード**（KPI4枚 + 棒グラフ2本） | **新規** |
| HTML UI | `/inventory` | 在庫一覧（旧 `/`） | **URL変更** |
| その他 | `/stock`（JSON）系 | petlife-streamlit互換のJSON API | **変更なし** |

## ダッシュボードの中身

- **KPIカード4枚**：総商品数 / 要発注（現在庫数 < 発注点）/ 当月末までに期限 / カテゴリ数
- **棒グラフ2本**：カテゴリ別商品数（青）/ 保管場所別商品数（オレンジ）
- **ナビゲーション**：ダッシュボード ↔ 在庫一覧 のタブ風リンク

## ファイル構成（差分）

```
templates/
  base.html                ← 変更なし
  dashboard.html           ← 新設
  inventory.html           ← index.html からリネーム + nav 追加
  _rows.html / _row.html / _qty_edit_cell.html ← 変更なし

static/
  style.css                ← 追記（ナビ + KPI + グラフカード）
  dashboard.js             ← 新設（Chart.js 初期化、純JS）

stock.csv                  ← 3件の消費期限を 2026-05/末 範囲に書き換え（KPI テスト用）
main.py                    ← 集計関数3つ + ルート2つ（dashboard / inventory）追加
```

## 設計上の判断ポイント

### 1. データアイランド方式（Python → JS のデータ受け渡し）

CLAUDE.md 既存学び「`<script>` の中にテンプレート記法を書かない」を守るため、`<script type="application/json">` を「データ専用の入れ物」として使う。

```html
<script id="category-data" type="application/json">{{ category_data | tojson }}</script>
<script src="/static/dashboard.js"></script>
```

JS 側で：

```js
const categoryData = JSON.parse(
    document.getElementById("category-data").textContent
);
```

これで `dashboard.js` は **テンプレート記法ゼロ** の純JS にできる。VSCode の JS Language Service もフルで効く。Django や Rails でも標準のパターン。

### 2. URL設計：`/stock` の取り合い問題

最初は「ダッシュボードを `/`、在庫一覧を `/stock`」と考えたが、`/stock` は既存の JSON API で使用中（petlife-streamlit が叩く）。**URL がぶつかる**ことに気付き、4案を検討して最終的に：

- ダッシュボード = `/`
- 在庫一覧 = `/inventory`（英語語彙は IT で広く通じる）
- JSON API は `/stock`, `/stock/{sku}` のまま（streamlit 互換維持）

**学び**: ルートを増やすときは、既存ルートとの衝突チェックを **設計段階で** やる。

### 3. レイアウト：`body { height: 100vh; flex column }` の使い回し

既存 inventory（旧 index）の「ヘッダー固定 + 中身スクロール」構造をそのまま使えるよう、ダッシュボードも `<header>` + `.dashboard-body` の2段構造に。`.dashboard-body { flex: 1; overflow-y: auto }` で `.table-wrapper` と同じパターン。

### 4. Chart.js のサイズ制御

`maintainAspectRatio: false` にすると Chart.js は親要素の高さに従う。だから `.chart-wrapper { position: relative; height: 280px }` を必ず付ける。これを忘れると Chart.js が「際限なく縦に伸びる」現象が起きる。

### 5. KPI 4 色の意味付け

| KPI | 色 | 理由 |
|---|---|---|
| 総商品数 | 青 | 基本情報・ニュートラル |
| 要発注 | 赤 | 注意喚起・対応必要 |
| 当月末までに期限 | オレンジ | 注意・予告 |
| カテゴリ数 | 緑 | 分類・安心 |

ダッシュボードの色は「**意味のあるシグナル**」として使う。色をランダムに散らさない。

### 6. 「当月末まで」の日付計算

```python
import calendar
def _end_of_month(today):
    last_day = calendar.monthrange(today.year, today.month)[1]
    return date(today.year, today.month, last_day)
```

`calendar.monthrange(年, 月)` は `(月の初日の曜日, その月の日数)` のタプルを返す。日本の月末は 28/29/30/31 と揺れるので、ハードコードせず標準ライブラリに任せる。

### 7. pandas の NaT を比較に使うと自然に除外される

```python
exp = pd.to_datetime(_df["消費期限"], errors="coerce")  # 不正値は NaT
expiring = int(((exp >= today_ts) & (exp <= eom_ts)).sum())
```

CSV で `消費期限` が空欄の行（おもちゃ等）は `NaT` になり、比較演算で `False` になる → 自然に除外される。**空欄チェックの if 文を書かなくていい**のが pandas の便利なところ。

## 新習得用語メモ

- **データアイランド (data island)**：`<script type="application/json">` を「ただのテキスト保管庫」として使う設計パターン。サーバーで生成した JSON をクライアント JS に渡す業界標準
- **Chart.js**：JavaScript の棒グラフ・円グラフ・折れ線グラフライブラリ。CDN 1行で使える。`new Chart(canvas要素, config)` でグラフを描く
- **`|tojson` (Jinja2 フィルタ)**：Python の dict/list を JS で読める JSON 文字列に変換する。HTML エスケープも兼ねるので安全
- **`calendar.monthrange(年, 月)`**：Python 標準ライブラリ。`(月の初日の曜日, その月の日数)` を返す。月末日の計算に必須
- **`pd.to_datetime(列, errors="coerce")`**：pandas の日付パース。`errors="coerce"` で不正値を `NaT` に変換（例外を投げない）
- **NaT (Not a Time)**：pandas の「日付の NaN」。比較演算では常に False を返すので、空欄が自然に除外される
- **CSS Grid (`grid-template-columns: repeat(4, 1fr)`)**：4列等幅レイアウト。Flexbox より行列指定が楽。`@media (max-width: 900px)` で 2列、`480px` で 1列にレスポンシブ
- **`maintainAspectRatio: false` + 親要素 height**：Chart.js を「親要素のサイズに合わせる」モードにする定石
- **同じ URL のメソッド/コンテンツタイプ別の住み分け**：今回は HTML (`/inventory`) と JSON (`/stock`) で URL を分けた。RESTful には Accept ヘッダで切り替える方法もあるが、業務系では URL を分ける方がデバッグしやすい

---

# 2026-05-25 追記: CRUD一通り完成（削除 + 新規登録）

## ゴール

CRUD の **D**（Delete）と **C**（Create）を一気に実装して、**CRUD一通り完成** を達成。
ロードマップの 5/8 まで到達（残り：詳細ページ / 業務直結機能 / README+スクショ）。

## 変更内容

### 削除機能（D）

| 区分 | パス | 役割 | 状態 |
|---|---|---|---|
| HTML UI | `DELETE /ui/stock/{sku}` | 商品削除 + 空HTML返却 | **新規** |

ファイル：
- `main.py`: `DELETE /ui/stock/{sku}` エンドポイント追加
- `templates/_row.html`: 削除ボタン `<td>` を追加（`hx-delete` + `hx-confirm` + `hx-swap="outerHTML swap:300ms"`）
- `templates/inventory.html`: `<colgroup>` と `<thead>` に「操作」列を追加
- `templates/_rows.html`: 0件メッセージの `colspan="8"` → `"9"` に
- `static/style.css`: `.btn-danger-sm` / `.actions` / `tr.htmx-swapping`（フェードアウト）追加

### 新規登録機能（C）

| 区分 | パス | 役割 | 状態 |
|---|---|---|---|
| HTML UI | `GET /new` | 新規登録フォーム画面 | **新規** |
| HTML UI | `POST /ui/stock` | フォーム送信 → `/inventory` にリダイレクト | **新規** |

ファイル：
- `main.py`: `RedirectResponse` import 追加、`add_to_df` / `get_categories` / `get_locations` ヘルパー追加、`GET /new` + `POST /ui/stock` 追加
- `templates/new.html`: **新規作成**（datalist 付きフォーム + バリデーションエラー表示）
- `templates/inventory.html` / `templates/dashboard.html`: nav に「新規登録」リンク追加
- `static/style.css`: フォーム用 CSS Grid + エラー表示スタイル追加

## 設計上の判断ポイント

### 1. 物理削除 vs 論理削除

業務システムでは論理削除（`deleted_at` フラグ列）が標準だが、**今の petlife-api では物理削除のまま進める** ことを意識的に選択。理由：

- 商品マスタしかない時点では論理削除のメリットが薄い（販売履歴・入出荷履歴と紐付くデータがまだない）
- 論理削除には UNIQUE 制約の組み替え、復元 UI、`WHERE deleted_at IS NULL` の全クエリ書き換えなど **波及コストが大きい**
- 業務直結機能（案B）で履歴データを作るタイミングで論理削除に切り替える方が、**「履歴と整合性を取りたいので論理削除を導入」というストーリーが自然**

**論理削除の判断軸（業務での経験則）：**
1. 過去データとの参照関係があるか（販売履歴、注文履歴）
2. 法的保管義務があるか（経理データ等）
3. 「やっぱり戻したい」が業務上起きるか
4. 監査・コンプライアンス要件があるか

petlife-api の今は 1〜4 がほぼ該当しない → 物理削除で OK。

**現場のハイブリッド方式（参考）：**

| データの性質 | 削除方式 |
|---|---|
| マスタ（商品・顧客） | 論理削除（履歴と紐付くから） |
| 一時データ（カゴ・下書き） | 物理削除（履歴不要） |
| 操作ログ・監査ログ | 削除しない（append-only） |
| 個人情報（GDPR対応） | 物理削除 + 匿名化 |

### 2. 永続化レイヤーの概念

今の petlife-api は **「サーバープロセスが生きている間だけ削除されているように見える」** 状態。
ブラウザでの削除操作 → メモリ上の `_df` だけが変わる → `stock.csv` は無傷。
uvicorn 再起動で `load_df()` が CSV を読み直し → 元に戻る。

```
[ブラウザのキャッシュ]    ← Ctrl+Shift+R で無効化
       ↓
[FastAPI サーバー (uvicorn)]
  [メモリ上の _df] ← 削除はここに反映
       ↑ (起動時 1回だけ)
  [stock.csv] ← ここは無傷
```

これは **意図的な設計**：

- 練習中に「全部消した、データ作り直し…」が起きない安心感
- PostgreSQL 移行のタイミングで「永続化レイヤーが本物になる」体験ができるよう保留してある

Forguncy / kintone は裏で常に DB に保存しているので「サーバーメモリ vs 永続データ」を意識する機会がほぼない。今の petlife-api は意図的にこの境界を見せている。

### 3. URL名前空間

DELETE と POST の追加で URL 設計を整理：

| パス | 目的 |
|---|---|
| `/ui/*` | HTML / HTMX 用（フォーム submit や HTMX レスポンス） |
| `/stock/*` | JSON API（petlife-streamlit 互換） |

`POST /ui/stock` は HTML フォームから submit、`POST /stock` は将来 JSON 用に取っておく。

### 4. PRG パターン（POST-Redirect-GET）

新規登録の完了後は `RedirectResponse(url="/inventory", status_code=303)` で `/inventory` にリダイレクト。

**目的**: ブラウザの「戻る / 再読込」で同じ POST が再送されて **二重登録** する事故を防ぐ。
**ステータスコード**: `303 See Other` が POST 後のリダイレクトに対する HTTP 標準（`302` でも動くがブラウザ実装によって POST が再送される可能性あり）。

業務系では今でも王道のパターン。Forguncy だとフレームワーク内部で自動的にやってくれているので意識する機会が少ないが、自分でフォーム処理を書くときは必須。

### 5. datalist で「サジェスト付き自由入力」

カテゴリと保管場所は **既存リストから候補を出しつつ、自由入力も可** にする UI を採用。

```html
<input type="text" id="category" name="category"
       list="categories-list">
<datalist id="categories-list">
    <option value="ドライフード">
    <option value="ウェットフード">
    ...
</datalist>
```

ドロップダウン（select）より柔軟、完全自由入力よりミスタイプを減らせる。業務系では「既存のリストに合わせて欲しいけど、新カテゴリも追加できる」要件が多く、この UI が最適解になりがち。

### 6. バリデーション + 入力値保持パターン

フォーム送信でエラーがあった場合、**フォーム画面を再描画 + 前回の入力値を保持 + エラー文言を表示**。

サーバー側：
```python
form_data = { "sku": sku.strip(), "name": name.strip(), ... }
errors = {}  # フィールド名 → エラー文言
# バリデーション
# エラーがあれば
return templates.TemplateResponse(
    request=request,
    name="new.html",
    context={"form_data": form_data, "errors": errors, ...},
    status_code=400,
)
```

テンプレート側：
```jinja
<input value="{{ form_data.get('sku', '') }}">
{% if errors.get('sku') %}
    <span class="field-error">{{ errors['sku'] }}</span>
{% endif %}
```

「入力した値を保持」が UX 上必須。これがないと、エラーが出ると全部入力し直しで体験が最悪になる。

## 今回の新習得

### 1. pandas の行削除イディオム

```python
_df = _df[_df["列"] != 値].reset_index(drop=True)
```

- `_df[条件]` で条件を満たす行だけに絞り込み（**指定値以外** が残る）
- 再代入なので `global _df` が必要
- `reset_index(drop=True)` は抜けたインデックスを 0,1,2,... に振り直す。再代入で行が抜けると元のインデックスが残るので **必ずペアで**

### 2. pandas の行追加イディオム

```python
_df = pd.concat([_df, pd.DataFrame([new_row])], ignore_index=True)
```

- `pd.DataFrame([new_row])` で「1行だけの DataFrame」を作って
- `pd.concat` で縦に連結
- `ignore_index=True` で 0,1,2,... のインデックスを振り直す

旧来の `_df.append(...)` は pandas 2.x で廃止された。今は `concat` が正解。

### 3. `RedirectResponse` + 303

```python
from fastapi.responses import RedirectResponse
return RedirectResponse(url="/inventory", status_code=303)
```

`303 See Other` = 「POST のあとは別のメソッド（GET）で見に行ってください」の意味。HTTP の作法として、POST 後のリダイレクトは 303 が正解。

### 4. HTML5 `<input type="date">`

ブラウザがカレンダーピッカーを自動で出してくれる。送信される値は `"YYYY-MM-DD"` 形式の文字列。CSV と同じ形式なのでそのまま保存できる。

### 5. HTMX の hx-delete / hx-confirm / hx-swap

```html
<button class="btn-danger-sm"
        hx-delete="/ui/stock/{{ s['SKUコード'] }}"
        hx-target="closest tr"
        hx-swap="outerHTML swap:300ms"
        hx-confirm="商品 「{{ s['商品名'] }}」 を削除しますか？">
    削除
</button>
```

- `hx-delete`: DELETE メソッドで指定URLを叩く
- `hx-confirm`: ブラウザの `confirm()` ダイアログを出す
- `hx-target="closest tr"`: 自分から見て一番近い `<tr>` を対象に
- `hx-swap="outerHTML swap:300ms"`: 要素自体を置換、300ms のフェード時間付き
- サーバーが空HTML を返せば `<tr>` が空文字に置換 → 行が消える

CSS で `tbody tr.htmx-swapping { opacity: 0; transition: opacity 300ms ease-out }` を当てると、消える前にふわっと薄れる演出になる。

### 6. ブラウザのキャッシュ vs サーバーのメモリ状態

「削除した行が `Ctrl+Shift+R` でも復活しない」のは **キャッシュではなく**、サーバー側メモリ（`_df`）の状態が変わっているから。

| レイヤー | リセット方法 |
|---|---|
| ブラウザのキャッシュ | `Ctrl+Shift+R` |
| サーバーのメモリ（_df） | uvicorn 再起動（`load_df()` が CSV から読み直し） |
| CSV ファイル | エディタで直接編集 / Git で巻き戻し |

`Ctrl+Shift+R` は **ブラウザ側** のキャッシュ無効化なので、サーバーが「消えた状態」を返すと、ブラウザは何度更新しても同じ答えを受け取る。

## 残課題（次回以降）

- **詳細ページ / モーダル**（0.5ユニット、htmx-search の detail パターン流用）
- **業務直結機能（案B）**（1〜2ユニット、CSV ダウンロード / 消費期限アラート / 入出荷登録）
  - このタイミングで論理削除への切り替えを再検討
- **README + スクショ更新**（0.5〜1ユニット、案C のストーリーを織り込む）
- **main.py の APIRouter リファクタリング**（0.5〜1ユニット、`routers/` 配下に分割）

## Questions to clarify before starting the next task
- NOTES.mdもCLAUDE.mdも気づいたら500行越えで、あなたを実際に頼る時間が減ってる気がするので、まずこれを圧縮するか私が知識をためる分と分けて見直したい
- main.pyの行が数百行あって追いきれないため、次の課題の前に分割する方式に修正したい
- 新規追加のところで疑問◇カテゴリ等選択入力方式だが、これは普通は選択しない、なぜなら間違える可能性があるため。選択式のみと修正したい◇日付のところ11111/11/11を登録することができた→エラーになるのでは？◇ID入力が自由だが通常は規則性にそぐわないものはNGにすべきではないか？日本語だけとかも登録可になってるのが気になる◇登録ボタン押下時「登録しますか？」と聞いて、「登録しました」ってやったよ、というのをアピールしたほうがいい気がする、すぐに入ってしまってよくわからなくなります◇登録ボタン押下で一覧に戻ったら、その登録したものにフォーカスがあたる、というのはできるの？
- もう一つくらい入力から一覧まであるとなおよいかも、簡単な（例えばカテゴリみたいな）ものを追加更新できるものを追加するのはどうか
