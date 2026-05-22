"""
サンプルペッツライフ 在庫管理API + 在庫管理画面

【エンドポイント】
  [HTML UI（HTMX）]
  GET  /              → 在庫一覧画面（HTML）
  GET  /ui/rows       → 検索結果の部分HTML（HTMX用）

  [JSON API]
  GET  /health        → ヘルスチェック（旧 / から移動）
  GET  /stock         → 全在庫データ取得（JSON）
  GET  /stock/{sku}   → 1商品取得（JSON）
  PUT  /stock/{sku}   → 在庫数更新

【データ】
  stock.csv をメモリ上の DataFrame で管理（デモ用・再起動で初期値に戻る）
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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
# リクエストモデル
# =============================================================
class StockUpdateRequest(BaseModel):
    現在庫数: int


# =============================================================
# [HTML UI] エンドポイント
# =============================================================
@app.get("/", response_class=HTMLResponse, summary="在庫一覧画面（HTML）")
def index(request: Request):
    """トップページ: 検索フォーム + 全件テーブルを含む完全なHTMLを返す"""
    stocks = get_all_stocks()
    # カテゴリのドロップダウン用リスト（DISTINCT + ソート）
    categories = sorted(set(item["カテゴリ"] for item in stocks))
    return templates.TemplateResponse(
        request=request,
        name="index.html",
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
    row = _df[_df["SKUコード"] == sku_code]
    if row.empty:
        raise HTTPException(
            status_code=404,
            detail=f"SKUコード '{sku_code}' が見つかりません",
        )
    return row.fillna("").to_dict(orient="records")[0]


@app.put("/stock/{sku_code}", summary="在庫数更新")
def update_stock_quantity(sku_code: str, body: StockUpdateRequest):
    """指定SKUの現在庫数を更新する"""
    global _df
    if _df[_df["SKUコード"] == sku_code].empty:
        raise HTTPException(
            status_code=404,
            detail=f"SKUコード '{sku_code}' が見つかりません",
        )
    _df.loc[_df["SKUコード"] == sku_code, "現在庫数"] = body.現在庫数
    _df["要発注"] = _df["現在庫数"] < _df["発注点"]
    updated = _df[_df["SKUコード"] == sku_code].fillna("").to_dict(orient="records")[0]
    return {"message": "更新しました", "data": updated}
