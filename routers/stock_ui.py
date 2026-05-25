"""
HTMX 用エンドポイント（/ui/*）

  GET    /ui/rows                  検索結果の部分HTML
  GET    /ui/stock/{sku}/edit_qty  通常セル → 編集セル差し替え
  PUT    /ui/stock/{sku}/qty       在庫数更新 + 行全体 <tr> 返却
  POST   /ui/stock                 新規登録（PRG パターンで /inventory にリダイレクト）
  DELETE /ui/stock/{sku}           行削除（空HTMLを返してフェードアウト）

ここは「部分HTMLか、リダイレクトしか返さない」のがポイント。完全なHTMLページは
pages.py、JSON は stock_api.py が担当する。
"""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import store
from templating import templates


router = APIRouter()


# -------------------------------------------------------------
# 検索結果の部分HTML（在庫一覧の絞り込み）
# -------------------------------------------------------------
@router.get("/ui/rows", response_class=HTMLResponse, summary="検索結果の部分HTML（HTMX用）")
def ui_rows(
    request: Request,
    category: str = "",
    keyword: str = "",
    low_only: bool = False,
):
    """HTMX が差し込む <tbody> の中身だけを返す"""
    results = store.filter_stocks(category, keyword, low_only)
    return templates.TemplateResponse(
        request=request,
        name="_rows.html",
        context={"stocks": results},
    )


# -------------------------------------------------------------
# インライン編集（CRUD の U）
# -------------------------------------------------------------
# 「現在庫数」セルのインライン編集を実現する2エンドポイント。
#   GET /ui/stock/{sku}/edit_qty … 通常セル → 編集セルに差し替え
#   PUT /ui/stock/{sku}/qty      … 在庫数を更新して 行全体 を返す
#
# 在庫数が変わると 要発注 フラグ（行全体の色 + フラグ列）も連動して変わるため、
# PUT のレスポンスは 1セルではなく 行全体 (_row.html) を返す方が確実。

@router.get(
    "/ui/stock/{sku_code}/edit_qty",
    response_class=HTMLResponse,
    summary="編集モードのセルHTMLを返す（HTMX用）",
)
def ui_edit_qty(request: Request, sku_code: str):
    """通常セル <td>12</td> を 編集セル <td><input ...></td> に差し替えるための部分HTML"""
    stock = store.get_stock_or_404(sku_code)
    return templates.TemplateResponse(
        request=request,
        name="_qty_edit_cell.html",
        context={"s": stock},
    )


@router.put(
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
    updated = store.update_qty_in_df(sku_code, qty)
    return templates.TemplateResponse(
        request=request,
        name="_row.html",
        context={"s": updated},
    )


# -------------------------------------------------------------
# 削除（CRUD の D）
# -------------------------------------------------------------
# HTMX 流の削除パターン:
#   - クライアントは <tr> 自体を対象にする（hx-target="closest tr", hx-swap="outerHTML"）
#   - サーバーは「削除後の置き換え内容」を返す
#   - 空HTML を返せば、<tr> が空文字に置き換わって行ごと消える

@router.delete(
    "/ui/stock/{sku_code}",
    response_class=HTMLResponse,
    summary="商品を削除して空HTMLを返す（HTMX用）",
)
def ui_delete_stock(sku_code: str):
    """指定SKUを削除して、空HTMLを返す（<tr> が空文字に置き換わって行が消える）"""
    store.delete_from_df(sku_code)
    return HTMLResponse(content="")


# -------------------------------------------------------------
# 新規登録（CRUD の C）
# -------------------------------------------------------------
# 古典的な「フォーム画面 + POST受け」の構成。
# HTMX は使わず、サーバー側で「成功時はリダイレクト」「エラー時はフォーム再描画」する
# PRG パターン（POST-Redirect-GET）を採用。業務系の登録画面の王道。
# フォーム画面（GET /new）は pages.py 側にある。

@router.post("/ui/stock", response_class=HTMLResponse, summary="商品を新規登録（HTMLフォーム送信）")
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
    elif store.sku_exists(sku_clean):
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
                "categories": store.get_categories(),
                "locations": store.get_locations(),
                "form_data": form_data,
                "errors": errors,
            },
            status_code=400,
        )

    # --- 登録 → /inventory にリダイレクト（PRG パターン） ---
    store.add_to_df({
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
