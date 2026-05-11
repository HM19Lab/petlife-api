"""
サンプルペッツライフ 在庫管理API
FastAPI バックエンド

【エンドポイント】
  GET  /              → ヘルスチェック
  GET  /stock         → 全在庫データ取得
  GET  /stock/{sku}   → 1商品取得（ルックアップ用）
  PUT  /stock/{sku}   → 在庫数更新

【データ】
  stock.csv を読み込んでメモリ上で管理
  ※ デモ用のため再起動で初期化されます
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import os

# =============================================================
# アプリ初期化
# =============================================================
app = FastAPI(
    title="サンプルペッツライフ 在庫API",
    description="ペットショップ在庫管理システムのバックエンドAPI",
    version="1.0.0"
)

# CORS設定（Streamlit Community CloudなどどのオリジンからもOK）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "PUT"],
    allow_headers=["*"],
)

# =============================================================
# CSVの読み込み
# =============================================================
CSV_PATH = os.path.join(os.path.dirname(__file__), "stock.csv")

COLUMNS = [
    "SKUコード", "商品名", "カテゴリ", "保管場所",
    "現在庫数", "発注点", "最新入荷日", "最新販売日", "消費期限", "備考"
]

def load_df() -> pd.DataFrame:
    """CSVを読み込んで整形したDataFrameを返す"""
    df = pd.read_csv(CSV_PATH, header=0)
    df.columns = COLUMNS
    df["現在庫数"] = pd.to_numeric(df["現在庫数"], errors="coerce").fillna(0).astype(int)
    df["発注点"]   = pd.to_numeric(df["発注点"],   errors="coerce").fillna(0).astype(int)
    df["要発注"]   = df["現在庫数"] < df["発注点"]
    return df

# メモリ上のDataFrame（デモ用。再起動で初期値に戻る）
_df: pd.DataFrame = load_df()


# =============================================================
# リクエストモデル
# =============================================================
class StockUpdateRequest(BaseModel):
    現在庫数: int


# =============================================================
# エンドポイント
# =============================================================
@app.get("/", summary="ヘルスチェック")
def root():
    return {
        "service": "サンプルペッツライフ 在庫API",
        "version": "1.0.0",
        "status": "ok"
    }


@app.get("/stock", summary="全在庫データ取得")
def get_all_stock():
    """全商品の在庫データをリストで返す"""
    return _df.fillna("").to_dict(orient="records")


@app.get("/stock/{sku_code}", summary="1商品の在庫データ取得")
def get_stock_item(sku_code: str):
    """SKUコードを指定して1商品のデータを返す（ルックアップ用）"""
    row = _df[_df["SKUコード"] == sku_code]
    if row.empty:
        raise HTTPException(
            status_code=404,
            detail=f"SKUコード '{sku_code}' が見つかりません"
        )
    return row.fillna("").to_dict(orient="records")[0]


@app.put("/stock/{sku_code}", summary="在庫数更新")
def update_stock_quantity(sku_code: str, body: StockUpdateRequest):
    """指定SKUの現在庫数を更新する"""
    global _df
    if _df[_df["SKUコード"] == sku_code].empty:
        raise HTTPException(
            status_code=404,
            detail=f"SKUコード '{sku_code}' が見つかりません"
        )
    _df.loc[_df["SKUコード"] == sku_code, "現在庫数"] = body.現在庫数
    _df["要発注"] = _df["現在庫数"] < _df["発注点"]
    updated = _df[_df["SKUコード"] == sku_code].fillna("").to_dict(orient="records")[0]
    return {"message": "更新しました", "data": updated}
