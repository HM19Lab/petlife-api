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

- **Railway 再デプロイ**：GitHub に push すれば自動デプロイされるはず。本番のライブ画面で動作確認
- **README のスクショ更新**：「API + 画面 一体型」になった旨を反映
- **インライン編集機能**（ステップD候補）：在庫数のセルをクリック → 編集 → 既存 PUT で更新
- **petlife-streamlit との役割整理**：HTMX 画面ができたので、Streamlit 版の位置づけを再検討（残す/廃止/役割限定）
