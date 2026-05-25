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
├── main.py                    FastAPI 本体（全エンドポイント）
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
    ├── _row.html              1行ぶんの <tr>（HTMX 単行差し替えで使い回し）
    └── _qty_edit_cell.html    在庫数の編集モードセル
```

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

### 7. 部分テンプレートの粒度

- `_rows.html` = 全行
- `_row.html` = 1行（HTMX レスポンスでも使い回し）
- `_qty_edit_cell.html` = 1セル

ファイル名のアンダースコア + 単数形/複数形で粒度がひと目でわかる。

---

## 残課題（次回以降）

| # | タスク | 工数 | メモ |
|---|---|---|---|
| **1** | **main.py の APIRouter リファクタリング**（`routers/` 配下に分割） | 0.5〜1ユニット | **最優先**。これを先にやると後続タスク全部のトークン消費が減る + ポートフォリオの見栄えも向上 |
| 2 | 詳細ページ / モーダル（htmx-search の detail パターン流用） | 0.5ユニット | 分割後の `routers/stock.py` に追加 |
| 3 | 業務直結機能（CSV ダウンロード / 消費期限アラート / 入出荷登録） | 1〜2ユニット | 新しい `routers/exports.py` / `routers/transactions.py` として追加。**このタイミングで論理削除への切り替えを再検討** |
| 4 | README + スクショ更新 | 0.5〜1ユニット | 全機能完成後にまとめて |
| 5 | （将来）PostgreSQL 移行 + 論理削除への切り替え | — | 業務直結機能と連動 |
| 6 | （将来）ログイン認証 + pytest による単体テスト | — | PetLife の bcrypt 経験を活用 |

### 新規登録の改善案（2026-05-25 でストック）

- カテゴリは選択式に変える検討（選択ミスを防ぐ）
- 日付バリデーション強化（11111/11/11 等を弾く）
- ID 入力の規則性チェック（日本語だけはNGなど）
- 登録ボタンの「登録しますか？」「登録しました」フィードバック
- 登録後、一覧でその商品にフォーカスがあたる UI
