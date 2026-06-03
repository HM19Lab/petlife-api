"""
マスタ管理（カテゴリ / 保管場所）

URL 設計：
  GET    /masters/categories                一覧ページ（HTML）
  GET    /masters/locations                 一覧ページ（HTML）
  POST   /ui/masters/{kind}                 新規追加（HTMX）
  PUT    /ui/masters/{kind}/{id}            更新（HTMX）
  DELETE /ui/masters/{kind}/{id}            削除（使用中ならブロック）
  GET    /ui/masters/{kind}/{id}/edit       行 → 編集モード切替

  kind = "categories" or "locations"

設計メモ：
  - kind を URL パラメータで受けて、store 側のヘルパーを動的に切り替える
  - これによりカテゴリ用と保管場所用でほぼ同じコードを書かずに済む
  - テンプレートも _master_row.html を共通化
"""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

import store
from templating import templates

router = APIRouter()


# =============================================================
# kind パラメータ → store 関数のルックアップ
# =============================================================
# URL の {kind} 値をキーに、store 側のヘルパーをまとめて引けるようにする辞書。
# kind が想定外の値（例: /masters/foo）なら 404 を返す。
KIND_MAP = {
    "categories": {
        "label": "カテゴリ",
        "get_all": store.get_all_categories,
        "add": store.add_category,
        "update": store.update_category,
        "delete": store.delete_category,
        "count_usage": store.count_category_usage,
    },
    "locations": {
        "label": "保管場所",
        "get_all": store.get_all_locations,
        "add": store.add_location,
        "update": store.update_location,
        "delete": store.delete_location,
        "count_usage": store.count_location_usage,
    },
}


def _resolve_kind(kind: str) -> dict:
    """kind から KIND_MAP のエントリを引く。未知の kind は 404"""
    if kind not in KIND_MAP:
        raise HTTPException(status_code=404, detail=f"unknown master kind: {kind}")
    return KIND_MAP[kind]


# =============================================================
# ページ表示（完全な HTML を返す）
# =============================================================
@router.get("/masters/categories", response_class=HTMLResponse, summary="カテゴリマスタ管理画面")
def page_categories(request: Request):
    return _render_master_page(request, "categories")


@router.get("/masters/locations", response_class=HTMLResponse, summary="保管場所マスタ管理画面")
def page_locations(request: Request):
    return _render_master_page(request, "locations")


def _attach_usage(items: list[dict], count_usage) -> list[dict]:
    """各 item に usage_count を付加して返す（テンプレートで item.usage_count を参照）"""
    for it in items:
        it["usage_count"] = count_usage(it["id"])
    return items


def _render_master_page(request: Request, kind: str) -> HTMLResponse:
    """マスタ管理ページの共通レンダリング"""
    config = _resolve_kind(kind)
    items = _attach_usage(config["get_all"](), config["count_usage"])
    return templates.TemplateResponse(
        request=request,
        name="masters.html",
        context={
            "kind": kind,
            "label": config["label"],
            "items": items,
        },
    )


# =============================================================
# HTMX：新規追加トリガー → 入力行への差し替え
# =============================================================
# トリガー行 → 入力行（_master_row_new.html）に差し替えるためのエンドポイント。
# /{id} 系より先に宣言しておく（id: int で型不一致だが、見通しのため固定パスを上に置く）。
@router.get("/ui/masters/{kind}/new-row", response_class=HTMLResponse, summary="新規入力行を返す")
def ui_get_master_new_row(request: Request, kind: str):
    config = _resolve_kind(kind)
    return templates.TemplateResponse(
        request=request,
        name="_master_row_new.html",
        context={"kind": kind, "label": config["label"]},
    )


# 入力行のキャンセル → トリガー行に戻す
@router.get("/ui/masters/{kind}/add-trigger", response_class=HTMLResponse, summary="トリガー行に戻す")
def ui_get_master_add_trigger(request: Request, kind: str):
    config = _resolve_kind(kind)
    return templates.TemplateResponse(
        request=request,
        name="_master_add_trigger.html",
        context={"kind": kind, "label": config["label"]},
    )


# =============================================================
# HTMX：新規追加
# =============================================================
@router.post("/ui/masters/{kind}", response_class=HTMLResponse, summary="マスタ新規追加")
def ui_add_master(
    request: Request,
    kind: str,
    name: str = Form(""),
    sort_order: str = Form(""),
    is_active: str = Form("on"),  # checkbox の慣習：チェック時 "on"、未チェックは送信されない
):
    config = _resolve_kind(kind)
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="名前は必須です")
    if len(name_clean) > 50:
        raise HTTPException(status_code=400, detail="名前は50文字以内で入力してください")

    sort_order_int: int | None = None
    if sort_order.strip():
        try:
            sort_order_int = int(sort_order.strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="表示順は数値で指定してください")

    config["add"](
        name=name_clean,
        sort_order=sort_order_int,
        is_active=(is_active == "on"),
    )
    # シフトで既存行の sort_order が変わっている可能性があるため、全行を返して
    # tbody innerHTML を丸ごと差し替える（HTMX 側で hx-swap="innerHTML"）
    items = _attach_usage(config["get_all"](), config["count_usage"])
    return templates.TemplateResponse(
        request=request,
        name="_master_rows.html",
        context={"kind": kind, "label": config["label"], "items": items},
    )


# =============================================================
# HTMX：編集モード切替（通常行 → 編集行）
# =============================================================
@router.get("/ui/masters/{kind}/{id}/edit", response_class=HTMLResponse, summary="編集モード切替")
def ui_edit_master_row(request: Request, kind: str, id: int):
    config = _resolve_kind(kind)
    items = config["get_all"]()
    target = next((x for x in items if x["id"] == id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"ID '{id}' が見つかりません")
    return templates.TemplateResponse(
        request=request,
        name="_master_row_edit.html",
        context={"kind": kind, "item": target},
    )


# =============================================================
# HTMX：行キャンセル（編集行 → 通常行）
# =============================================================
@router.get("/ui/masters/{kind}/{id}", response_class=HTMLResponse, summary="行を通常モードで再取得")
def ui_get_master_row(request: Request, kind: str, id: int):
    config = _resolve_kind(kind)
    items = config["get_all"]()
    target = next((x for x in items if x["id"] == id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"ID '{id}' が見つかりません")
    target["usage_count"] = config["count_usage"](id)
    return templates.TemplateResponse(
        request=request,
        name="_master_row.html",
        context={"kind": kind, "item": target},
    )


# =============================================================
# HTMX：更新
# =============================================================
@router.put("/ui/masters/{kind}/{id}", response_class=HTMLResponse, summary="マスタ更新")
def ui_update_master(
    request: Request,
    kind: str,
    id: int,
    name: str = Form(""),
    sort_order: str = Form("0"),
    is_active: str = Form(""),
):
    config = _resolve_kind(kind)
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="名前は必須です")
    if len(name_clean) > 50:
        raise HTTPException(status_code=400, detail="名前は50文字以内で入力してください")
    try:
        sort_order_int = int(sort_order.strip() or "0")
    except ValueError:
        raise HTTPException(status_code=400, detail="表示順は数値で指定してください")

    # 無効化ブロック：現在 active で、新値が inactive、かつ使用中なら拒否
    new_is_active = (is_active == "on")
    current = next((x for x in config["get_all"]() if x["id"] == id), None)
    if current and current["is_active"] and not new_is_active:
        usage = config["count_usage"](id)
        if usage > 0:
            return HTMLResponse(
                content=f"{usage} 件の商品で使用中のため無効化できません。先に該当商品のカテゴリ/保管場所を変更してください。",
                status_code=409,
            )

    config["update"](
        id_=id,
        name=name_clean,
        sort_order=sort_order_int,
        is_active=new_is_active,
    )
    # 更新でも sort_order シフトの影響が他行に出るため、全行を返して差し替え
    items = _attach_usage(config["get_all"](), config["count_usage"])
    return templates.TemplateResponse(
        request=request,
        name="_master_rows.html",
        context={"kind": kind, "label": config["label"], "items": items},
    )


# =============================================================
# HTMX：削除（使用中ならブロック）
# =============================================================
@router.delete("/ui/masters/{kind}/{id}", response_class=HTMLResponse, summary="マスタ削除")
def ui_delete_master(request: Request, kind: str, id: int):
    config = _resolve_kind(kind)
    usage = config["count_usage"](id)
    if usage > 0:
        # 削除をブロック。エラー行を返してユーザに伝える
        items = config["get_all"]()
        target = next((x for x in items if x["id"] == id), None)
        if not target:
            raise HTTPException(status_code=404, detail=f"ID '{id}' が見つかりません")
        target["usage_count"] = usage
        return templates.TemplateResponse(
            request=request,
            name="_master_row.html",
            context={
                "kind": kind,
                "item": target,
                "error": f"{usage} 件の商品で使用中のため削除できません",
            },
            status_code=409,
        )
    config["delete"](id)
    # 行を消す：空の HTML を返して HTMX に <tr> 自体を削除させる
    return HTMLResponse(content="")
