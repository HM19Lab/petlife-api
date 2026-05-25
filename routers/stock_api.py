"""
JSON API エンドポイント（petlife-streamlit 互換のため変更不可）

  GET /health        ヘルスチェック
  GET /stock         全在庫JSON
  GET /stock/{sku}   1件取得
  PUT /stock/{sku}   在庫数更新（JSON）

petlife-streamlit（別リポジトリのStreamlit版UI）がこのJSON URLを叩いているので、
パスもレスポンス形式も変えてはいけない。HTMX 用のエンドポイントは stock_ui.py
に分離して /ui/* の名前空間を使っている。
"""

from fastapi import APIRouter
from pydantic import BaseModel

import store


router = APIRouter()


# =============================================================
# リクエストモデル
# =============================================================
class StockUpdateRequest(BaseModel):
    現在庫数: int


# =============================================================
# エンドポイント
# =============================================================
@router.get("/health", summary="ヘルスチェック")
def health():
    """サービスの稼働確認用（旧 / から移動）"""
    return {
        "service": "サンプルペッツライフ 在庫API",
        "version": "1.1.0",
        "status": "ok",
    }


@router.get("/stock", summary="全在庫データ取得（JSON）")
def get_all_stock():
    """全商品の在庫データをリストで返す"""
    return store.get_all_stocks()


@router.get("/stock/{sku_code}", summary="1商品の在庫データ取得（JSON）")
def get_stock_item(sku_code: str):
    """SKUコードを指定して1商品のデータを返す"""
    return store.get_stock_or_404(sku_code)


@router.put("/stock/{sku_code}", summary="在庫数更新（JSON、petlife-streamlit 互換）")
def update_stock_quantity(sku_code: str, body: StockUpdateRequest):
    """指定SKUの現在庫数を更新する（JSONバージョン）"""
    updated = store.update_qty_in_df(sku_code, body.現在庫数)
    return {"message": "更新しました", "data": updated}
