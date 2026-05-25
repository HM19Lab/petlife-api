"""
サンプルペッツライフ 在庫管理API + 在庫管理画面 + ダッシュボード

【エンドポイント】
  [HTML UI（HTMX）]
  GET  /                        → ダッシュボード画面（KPI + Chart.js グラフ）
  GET  /inventory               → 在庫一覧画面（HTML、旧 /）
  GET  /new                     → 新規登録フォーム画面（HTML）
  GET  /ui/rows                 → 検索結果の部分HTML（HTMX用）
  GET  /ui/stock/{sku}/edit_qty → 編集モードのセル（HTMX用）
  PUT  /ui/stock/{sku}/qty      → 在庫数更新＋行HTML返却（HTMX用）
  DELETE /ui/stock/{sku}        → 商品削除＋空HTML返却（HTMX用）
  POST /ui/stock                → 新規登録（HTMLフォーム送信）→ /inventory にリダイレクト

  [JSON API]（petlife-streamlit 互換のため変更なし）
  GET  /health        → ヘルスチェック
  GET  /stock         → 全在庫データ取得（JSON）
  GET  /stock/{sku}   → 1商品取得（JSON）
  PUT  /stock/{sku}   → 在庫数更新（JSON）

【データ】
  stock.csv をメモリ上の DataFrame で管理（デモ用・再起動で初期値に戻る）
"""

from datetime import date
import calendar
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import pandas as pd

# =============================================================
# アプリ初期化
# =============================================================
app = FastAPI(
    title="サンプルペッツライフ 在庫API",
    description="ペットショップ在庫管理システム（API + HTMX画面）",
    version="1.1.0",
)

# CORS設定（既存の petlife-streamlit から呼ばれるので維持）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "PUT"],
    allow_headers=["*"],
)

# Jinja2 テンプレート設定（htmx-search と同じパターン）
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# 静的ファイル（CSS / 画像など）の配信設定
# 「/static/foo.css」というURLが来たら ./static/foo.css を返す、という設定。
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# =============================================================
# CSVの読み込み
# =============================================================
CSV_PATH = BASE_DIR / "stock.csv"

COLUMNS = [
    "SKUコード", "商品名", "カテゴリ", "保管場所",
    "現在庫数", "発注点", "最新入荷日", "最新販売日", "消費期限", "備考",
]


def load_df() -> pd.DataFrame:
    """CSVを読み込んで整形したDataFrameを返す"""
    df = pd.read_csv(CSV_PATH, header=0)
    df.columns = COLUMNS
    df["現在庫数"] = pd.to_numeric(df["現在庫数"], errors="coerce").fillna(0).astype(int)
    df["発注点"] = pd.to_numeric(df["発注点"], errors="coerce").fillna(0).astype(int)
    df["要発注"] = df["現在庫数"] < df["発注点"]
    return df


# メモリ上のDataFrame（デモ用。再起動で初期値に戻る）
_df: pd.DataFrame = load_df()


# =============================================================
# 補助関数（HTML側・JSON側の両方から使う）
# =============================================================
def get_all_stocks() -> list[dict]:
    """DataFrame を dict のリストに変換（テンプレート/JSON 両用）"""
    return _df.fillna("").to_dict(orient="records")


def update_qty_in_df(sku_code: str, qty: int) -> dict:
    """指定SKUの現在庫数を更新し、最新の1件(dict)を返す。

    在庫数を変えると 要発注 フラグ（現在庫数 < 発注点）も連動して切り替わるため、
    更新→フラグ再計算 をここで一括で行う。
    JSON版PUTと HTMX版PUT の両方から呼ぶ共通処理。
    """
    global _df
    if _df[_df["SKUコード"] == sku_code].empty:
        raise HTTPException(
            status_code=404,
            detail=f"SKUコード '{sku_code}' が見つかりません",
        )
    _df.loc[_df["SKUコード"] == sku_code, "現在庫数"] = qty
    _df["要発注"] = _df["現在庫数"] < _df["発注点"]
    return _df[_df["SKUコード"] == sku_code].fillna("").to_dict(orient="records")[0]


def get_stock_or_404(sku_code: str) -> dict:
    """1件取得。なければ404。テンプレート用のdictを返す。"""
    row = _df[_df["SKUコード"] == sku_code]
    if row.empty:
        raise HTTPException(
            status_code=404,
            detail=f"SKUコード '{sku_code}' が見つかりません",
        )
    return row.fillna("").to_dict(orient="records")[0]


def add_to_df(new_row: dict) -> None:
    """新しい商品を DataFrame に追加する。

    pandas の行追加イディオム:
      _df = pd.concat([_df, pd.DataFrame([new_row])], ignore_index=True)
      - pd.DataFrame([new_row]) で「1行だけのDataFrame」を作って
      - pd.concat で縦に連結
      - ignore_index=True で 0,1,2,... のインデックスを振り直し

    要発注 フラグも全行ぶん再計算する（更新時と同じ）。
    再代入なので global _df が必要。
    """
    global _df
    _df = pd.concat([_df, pd.DataFrame([new_row])], ignore_index=True)
    _df["要発注"] = _df["現在庫数"] < _df["発注点"]


def get_categories() -> list[str]:
    """カテゴリのDISTINCTリスト（ソート済み）。datalist の候補に使う。"""
    return sorted(set(_df["カテゴリ"].dropna().tolist()))


def get_locations() -> list[str]:
    """保管場所のDISTINCTリスト（ソート済み）。datalist の候補に使う。"""
    return sorted(set(_df["保管場所"].dropna().tolist()))


def filter_stocks(category: str, keyword: str, low_only: bool) -> list[dict]:
    """検索条件で在庫を絞り込む

    - category: 完全一致（"" なら絞り込みなし）
    - keyword:  SKUコード/商品名/保管場所のいずれかに部分一致
    - low_only: True なら 要発注 のみ
    """
    results = []
    for item in get_all_stocks():
        # カテゴリ絞り込み
        if category and item["カテゴリ"] != category:
            continue
        # キーワード絞り込み（SKU/商品名/保管場所のどれかにヒット）
        if keyword:
            target = (
                str(item["SKUコード"])
                + " " + str(item["商品名"])
                + " " + str(item["保管場所"])
            )
            if keyword not in target:
                continue
        # 要発注のみフィルタ
        if low_only and not item["要発注"]:
            continue
        results.append(item)
    return results


# =============================================================
# ダッシュボード用 集計関数
# =============================================================
# トップページ「/」のダッシュボードで使う4つのKPIと
# Chart.js 用のグラフデータ（カテゴリ別/保管場所別）を集計する。
# pandas の groupby / 日付フィルタ を使って DataFrame から直接計算する。

def _end_of_month(today: date) -> date:
    """当月末の日付を返す。例: 2026-05-24 → 2026-05-31

    calendar.monthrange(年, 月) は (月の初日の曜日, その月の日数) を返す。
    [1] で日数だけ取り出して、その日付を組み立てる。
    """
    last_day = calendar.monthrange(today.year, today.month)[1]
    return date(today.year, today.month, last_day)


def get_dashboard_stats(today: date | None = None) -> dict:
    """ダッシュボード用KPI 4枚分の数値を返す

    返り値の dict のキー:
      - total:      総商品数
      - low:        要発注数（現在庫数 < 発注点）
      - expiring:   当月末までに消費期限が来る商品数
      - categories: カテゴリ数（DISTINCT）
      - today_iso:  今日の日付（テンプレート表示用、ISO形式）
      - eom_iso:    当月末の日付（テンプレート表示用、ISO形式）

    today を引数で渡せるようにしておくと、テストや「過去日付で動作確認」がしやすい。
    渡さなければ date.today() を使う。
    """
    today = today or date.today()
    eom = _end_of_month(today)

    total = len(_df)
    low = int(_df["要発注"].sum())

    # 消費期限を日付型に変換。空文字や不正値は NaT（pandas の Not a Time）になり、
    # 比較演算で False になるので自然に除外される。
    exp = pd.to_datetime(_df["消費期限"], errors="coerce")
    today_ts = pd.Timestamp(today)
    eom_ts = pd.Timestamp(eom)
    expiring = int(((exp >= today_ts) & (exp <= eom_ts)).sum())

    categories = int(_df["カテゴリ"].nunique())
    total_qty = int(_df["現在庫数"].sum())

    return {
        "total": total,
        "low": low,
        "expiring": expiring,
        "categories": categories,
        "total_qty": total_qty,
        "today_iso": today.isoformat(),
        "eom_iso": eom.isoformat(),
    }


def get_category_counts() -> list[dict]:
    """カテゴリ別の商品数を集計（Chart.js の棒グラフ用）

    返り値の例: [{"label": "ドライフード", "count": 5}, ...]
    商品数が多い順に並べる（降順ソート）。
    """
    counts = _df.groupby("カテゴリ").size().sort_values(ascending=False)
    return [{"label": k, "count": int(v)} for k, v in counts.items()]


def get_location_counts() -> list[dict]:
    """保管場所別の商品数を集計（Chart.js の棒グラフ用）

    返り値の例: [{"label": "店舗A棚", "count": 7}, ...]
    商品数が多い順に並べる（降順ソート）。
    """
    counts = _df.groupby("保管場所").size().sort_values(ascending=False)
    return [{"label": k, "count": int(v)} for k, v in counts.items()]


# =============================================================
# リクエストモデル
# =============================================================
class StockUpdateRequest(BaseModel):
    現在庫数: int


# =============================================================
# [HTML UI] エンドポイント
# =============================================================
@app.get("/", response_class=HTMLResponse, summary="ダッシュボード画面（HTML）")
def dashboard(request: Request):
    """トップページ: KPIカード4枚 + Chart.js の棒グラフ2本

    集計関数で計算した数値を context に詰めて dashboard.html に渡す。
    Chart.js 用のグラフデータは Jinja2 の |tojson フィルタで JS 側に渡す。
    """
    stats = get_dashboard_stats()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "stats": stats,
            "category_data": get_category_counts(),
            "location_data": get_location_counts(),
        },
    )


@app.get("/inventory", response_class=HTMLResponse, summary="在庫一覧画面（HTML）")
def inventory(request: Request):
    """在庫一覧ページ: 検索フォーム + 全件テーブルを含む完全なHTMLを返す（旧 /）"""
    stocks = get_all_stocks()
    # カテゴリのドロップダウン用リスト（DISTINCT + ソート）
    categories = sorted(set(item["カテゴリ"] for item in stocks))
    return templates.TemplateResponse(
        request=request,
        name="inventory.html",
        context={"stocks": stocks, "categories": categories},
    )


@app.get("/ui/rows", response_class=HTMLResponse, summary="検索結果の部分HTML（HTMX用）")
def ui_rows(
    request: Request,
    category: str = "",
    keyword: str = "",
    low_only: bool = False,
):
    """HTMX が差し込む <tbody> の中身だけを返す"""
    results = filter_stocks(category, keyword, low_only)
    return templates.TemplateResponse(
        request=request,
        name="_rows.html",
        context={"stocks": results},
    )


# =============================================================
# [JSON API] エンドポイント（petlife-streamlit 互換のため変更なし）
# =============================================================
@app.get("/health", summary="ヘルスチェック")
def health():
    """サービスの稼働確認用（旧 / から移動）"""
    return {
        "service": "サンプルペッツライフ 在庫API",
        "version": "1.1.0",
        "status": "ok",
    }


@app.get("/stock", summary="全在庫データ取得（JSON）")
def get_all_stock():
    """全商品の在庫データをリストで返す"""
    return get_all_stocks()


@app.get("/stock/{sku_code}", summary="1商品の在庫データ取得（JSON）")
def get_stock_item(sku_code: str):
    """SKUコードを指定して1商品のデータを返す"""
    return get_stock_or_404(sku_code)


@app.put("/stock/{sku_code}", summary="在庫数更新（JSON、petlife-streamlit 互換）")
def update_stock_quantity(sku_code: str, body: StockUpdateRequest):
    """指定SKUの現在庫数を更新する（JSONバージョン）"""
    updated = update_qty_in_df(sku_code, body.現在庫数)
    return {"message": "更新しました", "data": updated}


# =============================================================
# [HTML UI] インライン編集用エンドポイント（ステップD）
# =============================================================
# 「現在庫数」セルのインライン編集を実現する2エンドポイント。
#   GET /ui/stock/{sku}/edit_qty … 通常セル → 編集セルに差し替え
#   PUT /ui/stock/{sku}/qty      … 在庫数を更新して 行全体 を返す
#
# 在庫数が変わると 要発注 フラグ（行全体の色 + フラグ列）も連動して変わるため、
# PUT のレスポンスは 1セルではなく 行全体 (_row.html) を返す方が確実。
#
# 既存 JSON 版 PUT /stock/{sku} は petlife-streamlit から呼ばれているので変更しない。
# HTMX 用は /ui/stock/... に名前空間を分けて互換性を守る。

@app.get(
    "/ui/stock/{sku_code}/edit_qty",
    response_class=HTMLResponse,
    summary="編集モードのセルHTMLを返す（HTMX用）",
)
def ui_edit_qty(request: Request, sku_code: str):
    """通常セル <td>12</td> を 編集セル <td><input ...></td> に差し替えるための部分HTML"""
    stock = get_stock_or_404(sku_code)
    return templates.TemplateResponse(
        request=request,
        name="_qty_edit_cell.html",
        context={"s": stock},
    )


@app.put(
    "/ui/stock/{sku_code}/qty",
    response_class=HTMLResponse,
    summary="在庫数を更新して行HTMLを返す（HTMX用）",
)
def ui_update_qty(
    request: Request,
    sku_code: str,
    qty: int = Form(...),
):
    """HTMX のフォーム送信を受けて、在庫数を更新 → 行全体(<tr>)を返す。

    入力バリデーション: 0 未満は 400 で弾く（HTMX は 4xx を受け取るとデフォルトで何もしない）。
    """
    if qty < 0:
        raise HTTPException(status_code=400, detail="在庫数は0以上で指定してください")
    updated = update_qty_in_df(sku_code, qty)
    return templates.TemplateResponse(
        request=request,
        name="_row.html",
        context={"s": updated},
    )


# =============================================================
# [HTML UI] 削除用エンドポイント（2026-05-25 / CRUD の D）
# =============================================================
# 各行の「削除」ボタンが叩く HTMX 用エンドポイント。
#
# HTMX 流の削除パターン（htmx-search で習得済み）:
#   - クライアントは <tr> 自体を対象にする（hx-target="closest tr", hx-swap="outerHTML"）
#   - サーバーは「削除後の置き換え内容」を返す
#   - 空HTML を返せば、<tr> が空文字に置き換わって行ごと消える
#
# 既存 JSON 版 /stock/{sku} には DELETE を生やさず、HTMX 用に名前空間を分ける
# （petlife-streamlit との互換性を守る方針はインライン編集と同じ）。

@app.delete(
    "/ui/stock/{sku_code}",
    response_class=HTMLResponse,
    summary="商品を削除して空HTMLを返す（HTMX用）",
)
def ui_delete_stock(sku_code: str):
    """指定SKUを DataFrame から削除して、空HTMLを返す。

    pandas の行削除イディオム:
        _df = _df[_df["列"] != 値].reset_index(drop=True)
      = 「指定値以外」を絞り込んだ DataFrame で _df を上書き。
        reset_index(drop=True) は抜けたインデックスを 0,1,2,... に振り直す。

    再代入なので global _df が必要（update_qty_in_df と同じ理由）。
    """
    global _df
    if _df[_df["SKUコード"] == sku_code].empty:
        raise HTTPException(
            status_code=404,
            detail=f"SKUコード '{sku_code}' が見つかりません",
        )
    _df = _df[_df["SKUコード"] != sku_code].reset_index(drop=True)
    # 空HTML を返す → <tr> が空文字に置き換わって行が消える
    return HTMLResponse(content="")


# =============================================================
# [HTML UI] 新規登録用エンドポイント（2026-05-25 / CRUD の C）
# =============================================================
# 古典的な「フォーム画面 + POST受け」の2エンドポイント構成。
# HTMX は使わず、サーバー側で「成功時はリダイレクト」「エラー時はフォーム再描画」する
# PRG パターン（POST-Redirect-GET）を採用。これは業務系の登録画面の王道。

@app.get("/new", response_class=HTMLResponse, summary="新規登録フォーム（HTML）")
def new_form(request: Request):
    """新規登録ページを返す。初回表示は form_data も errors も空。"""
    return templates.TemplateResponse(
        request=request,
        name="new.html",
        context={
            "categories": get_categories(),
            "locations": get_locations(),
            "form_data": {},
            "errors": {},
        },
    )


@app.post("/ui/stock", response_class=HTMLResponse, summary="商品を新規登録（HTMLフォーム送信）")
def ui_create_stock(
    request: Request,
    sku: str = Form(""),
    name: str = Form(""),
    category: str = Form(""),
    location: str = Form(""),
    current_qty: str = Form("0"),
    reorder_point: str = Form("0"),
    last_arrival: str = Form(""),
    last_sale: str = Form(""),
    expiry: str = Form(""),
    note: str = Form(""),
):
    """新規登録フォームのPOST受け口。

    成功時: 303 リダイレクトで /inventory に遷移（PRG パターン）。
    エラー時: 入力値を保持したまま new.html を再描画（400 ステータス）。

    入力値の数値変換は try/except で受ける。日付類はそのまま文字列で保存する
    （CSV と同じ "YYYY-MM-DD" 形式の文字列のまま）。
    """
    # --- バリデーション ---
    errors: dict[str, str] = {}

    sku_clean = sku.strip()
    if not sku_clean:
        errors["sku"] = "SKUコードは必須です"
    elif not _df[_df["SKUコード"] == sku_clean].empty:
        errors["sku"] = f"SKUコード '{sku_clean}' は既に登録されています"

    name_clean = name.strip()
    if not name_clean:
        errors["name"] = "商品名は必須です"

    # 数値項目: int() で変換 → ValueError なら入力ミス扱い
    try:
        qty_int = int(current_qty)
        if qty_int < 0:
            errors["current_qty"] = "現在庫数は0以上で指定してください"
    except ValueError:
        errors["current_qty"] = "現在庫数は数値で指定してください"
        qty_int = 0

    try:
        reorder_int = int(reorder_point)
        if reorder_int < 0:
            errors["reorder_point"] = "発注点は0以上で指定してください"
    except ValueError:
        errors["reorder_point"] = "発注点は数値で指定してください"
        reorder_int = 0

    # 入力値を辞書にまとめておく（エラー時の再描画でフォームに再挿入する）
    form_data = {
        "sku": sku_clean,
        "name": name_clean,
        "category": category.strip(),
        "location": location.strip(),
        "current_qty": current_qty.strip(),
        "reorder_point": reorder_point.strip(),
        "last_arrival": last_arrival.strip(),
        "last_sale": last_sale.strip(),
        "expiry": expiry.strip(),
        "note": note.strip(),
    }

    # --- エラーがあればフォームを再描画 ---
    if errors:
        return templates.TemplateResponse(
            request=request,
            name="new.html",
            context={
                "categories": get_categories(),
                "locations": get_locations(),
                "form_data": form_data,
                "errors": errors,
            },
            status_code=400,
        )

    # --- 登録 → /inventory にリダイレクト（PRG パターン） ---
    add_to_df({
        "SKUコード": sku_clean,
        "商品名": name_clean,
        "カテゴリ": form_data["category"],
        "保管場所": form_data["location"],
        "現在庫数": qty_int,
        "発注点": reorder_int,
        "最新入荷日": form_data["last_arrival"],
        "最新販売日": form_data["last_sale"],
        "消費期限": form_data["expiry"],
        "備考": form_data["note"],
    })
    # 303 See Other: POST のあとは別のメソッド（GET）で見に行ってください、の意味。
    # ブラウザの再読み込みで二重POSTが起きないようにする HTTP のお作法。
    return RedirectResponse(url="/inventory", status_code=303)
