"""
サンプルペッツライフ 在庫管理API + 在庫管理画面 + ダッシュボード

このファイルはアプリの「玄関」だけ。エンドポイント本体は routers/ 配下、
データ層は store.py、テンプレート初期化は templating.py に分離している。

【エンドポイント一覧】
  [画面HTML]                routers/pages.py
    GET  /                  → ダッシュボード（KPI + Chart.js）
    GET  /inventory         → 在庫一覧画面
    GET  /new               → 新規登録フォーム

  [マスタ管理画面]          routers/masters.py
    GET  /masters/categories → カテゴリマスタ
    GET  /masters/locations  → 保管場所マスタ
    POST/PUT/DELETE /ui/masters/{kind}/...

  [HTMX 用 /ui/*]           routers/stock_ui.py
    GET    /ui/rows                  → 検索結果の部分HTML
    GET    /ui/stock/{sku}/edit_qty  → 編集モードのセル
    PUT    /ui/stock/{sku}/qty       → 在庫数更新 + 行HTML
    DELETE /ui/stock/{sku}           → 商品削除 + 空HTML
    POST   /ui/stock                 → 新規登録 → /inventory リダイレクト

  [JSON API]                routers/stock_api.py（petlife-streamlit 互換）
    GET  /health
    GET  /stock
    GET  /stock/{sku}
    PUT  /stock/{sku}

【データ】
  stock.csv / categories.csv / locations.csv をメモリ上の DataFrame で管理
  （デモ用・再起動で初期値に戻る。次フェーズで SQLite 移行予定）
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers import pages, stock_ui, stock_api, masters


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
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# 静的ファイル配信（/static/foo.css → ./static/foo.css）
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


# =============================================================
# ルーター登録（include_router）
# =============================================================
# include_router で「子ルーターを本体アプリに合流させる」。
# prefix を付けないので、各ルーターが宣言したパスがそのまま有効になる。
# = リファクタ前と URL は完全に同一（streamlit互換も壊れない）
app.include_router(pages.router)
app.include_router(stock_ui.router)
app.include_router(stock_api.router)
app.include_router(masters.router)
