"""
画面HTML を返すエンドポイント

  GET /           → ダッシュボード（KPI + Chart.js）
  GET /inventory  → 在庫一覧画面
  GET /new        → 新規登録フォーム画面

ここはどれも「完全なHTMLページ」を返すルート（HTMX の部分HTMLは stock_ui.py）。
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from store import (
    get_all_stocks,
    get_active_categories,
    get_active_locations,
    get_dashboard_stats,
    get_category_counts,
    get_location_counts,
)
from templating import templates


router = APIRouter()


@router.get("/", response_class=HTMLResponse, summary="ダッシュボード画面（HTML）")
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


@router.get("/inventory", response_class=HTMLResponse, summary="在庫一覧画面（HTML）")
def inventory(request: Request):
    """在庫一覧ページ: 検索フォーム + 全件テーブルを含む完全なHTMLを返す（旧 /）"""
    stocks = get_all_stocks()
    # フィルタ用カテゴリは「マスタの有効分」（sort_order 順）
    categories = get_active_categories()
    return templates.TemplateResponse(
        request=request,
        name="inventory.html",
        context={"stocks": stocks, "categories": categories},
    )


@router.get("/new", response_class=HTMLResponse, summary="新規登録フォーム（HTML）")
def new_form(request: Request):
    """新規登録ページを返す。初回表示は form_data も errors も空。"""
    return templates.TemplateResponse(
        request=request,
        name="new.html",
        context={
            "categories": get_active_categories(),
            "locations": get_active_locations(),
            "form_data": {},
            "errors": {},
        },
    )
