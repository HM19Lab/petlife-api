"""HTMX 用エンドポイント (/ui/*)

  GET    /ui/rows
  GET    /ui/stock/{sku}/edit_qty
  GET    /ui/stock/{sku}/qty_cell    (blur キャンセル用)
  PUT    /ui/stock/{sku}/qty
  GET    /ui/stock/{sku}/detail
  PUT    /ui/stock/{sku}/full
  POST   /ui/stock
  DELETE /ui/stock/{sku}
"""

import re
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import store
from templating import templates

router = APIRouter()


@router.get("/ui/rows", response_class=HTMLResponse)
def ui_rows(request: Request, category: str = "", keyword: str = "", low_only: bool = False):
    results = store.filter_stocks(category, keyword, low_only)
    return templates.TemplateResponse(request=request, name="_rows.html", context={"stocks": results})


@router.get("/ui/stock/{sku_code}/edit_qty", response_class=HTMLResponse)
def ui_edit_qty(request: Request, sku_code: str):
    stock = store.get_stock_or_404(sku_code)
    return templates.TemplateResponse(request=request, name="_qty_edit_cell.html", context={"s": stock})


# blur キャンセル用: 通常モードの <td> を返す
@router.get("/ui/stock/{sku_code}/qty_cell", response_class=HTMLResponse)
def ui_qty_cell(request: Request, sku_code: str):
    stock = store.get_stock_or_404(sku_code)
    return templates.TemplateResponse(request=request, name="_qty_cell.html", context={"s": stock})


@router.put("/ui/stock/{sku_code}/qty", response_class=HTMLResponse)
def ui_update_qty(request: Request, sku_code: str, qty: int = Form(...)):
    if qty < 0:
        raise HTTPException(status_code=400, detail="qty must be >= 0")
    updated = store.update_qty_in_df(sku_code, qty)
    return templates.TemplateResponse(request=request, name="_row.html", context={"s": updated})


@router.get("/ui/stock/{sku_code}/detail", response_class=HTMLResponse)
def ui_stock_detail(request: Request, sku_code: str):
    stock = store.get_stock_or_404(sku_code)
    return templates.TemplateResponse(
        request=request,
        name="_modal.html",
        context={
            "s": stock,
            "categories": store.get_categories(),
            "locations": store.get_locations(),
        },
    )


@router.put("/ui/stock/{sku_code}/full", response_class=HTMLResponse)
def ui_update_full(
    request: Request,
    sku_code: str,
    name: str = Form(""),
    category: str = Form(""),
    location: str = Form(""),
    current_qty: int = Form(0),
    reorder_point: int = Form(0),
    last_arrival: str = Form(""),
    last_sale: str = Form(""),
    expiry: str = Form(""),
    note: str = Form(""),
):
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="name required")
    if current_qty < 0:
        raise HTTPException(status_code=400, detail="qty >= 0")
    if reorder_point < 0:
        raise HTTPException(status_code=400, detail="reorder >= 0")
    updated = store.update_item_in_df(sku_code, {
        "商品名": name_clean,
        "カテゴリ": category.strip(),
        "保管場所": location.strip(),
        "現在庫数": current_qty,
        "発注点": reorder_point,
        "最新入荷日": last_arrival.strip(),
        "最新販売日": last_sale.strip(),
        "消費期限": expiry.strip(),
        "備考": note.strip(),
    })
    return templates.TemplateResponse(request=request, name="_row.html", context={"s": updated, "oob": True})


@router.delete("/ui/stock/{sku_code}", response_class=HTMLResponse)
def ui_delete_stock(sku_code: str):
    store.delete_from_df(sku_code)
    return HTMLResponse(content="")


@router.post("/ui/stock", response_class=HTMLResponse)
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
    errors: dict[str, str] = {}
    sku_clean = sku.strip()
    if not sku_clean:
        errors["sku"] = "SKUコードは必須です"
    elif not re.fullmatch(r"[A-Za-z0-9\-]+", sku_clean):
        errors["sku"] = "SKUコードは半角英数とハイフンのみで入力してください"
    elif len(sku_clean) > 20:
        errors["sku"] = "SKUコードは20文字以内で入力してください"
    elif store.sku_exists(sku_clean):
        errors["sku"] = f"SKUコード '{sku_clean}' は既に登録されています"
    name_clean = name.strip()
    if not name_clean:
        errors["name"] = "商品名は必須です"
    elif len(name_clean) > 100:
        errors["name"] = "商品名は100文字以内で入力してください"
    
    current_qty_clean = current_qty.strip()
    if not current_qty_clean:
        errors["current_qty"] = "現在庫数は必須です"
        qty_int = 0
    else:
        try:
            qty_int = int(current_qty_clean)
            if qty_int < 0:
                errors["current_qty"] = "現在庫数は0以上で指定してください"
        except ValueError:
            errors["current_qty"] = "現在庫数は数値で指定してください"
            qty_int = 0
        
    reorder_clean = reorder_point.strip()
    if not reorder_clean:
        errors["reorder_point"] = "発注点は必須です"
        reorder_int = 0
    else:
        try:
            reorder_int = int(reorder_clean)
            if reorder_int < 0:
                errors["reorder_point"] = "発注点は0以上で指定してください"
        except ValueError:
            errors["reorder_point"] = "発注点は数値で指定してください"
            reorder_int = 0
    form_data = {
        "sku": sku_clean, "name": name_clean,
        "category": category.strip(), "location": location.strip(),
        "current_qty": current_qty.strip(), "reorder_point": reorder_point.strip(),
        "last_arrival": last_arrival.strip(), "last_sale": last_sale.strip(),
        "expiry": expiry.strip(), "note": note.strip(),
    }
    if errors:
        return templates.TemplateResponse(
            request=request, name="new.html",
            context={
                "categories": store.get_categories(),
                "locations": store.get_locations(),
                "form_data": form_data, "errors": errors,
            },
            status_code=400,
        )
    store.add_to_df({
        "SKUコード": sku_clean, "商品名": name_clean,
        "カテゴリ": form_data["category"], "保管場所": form_data["location"],
        "現在庫数": qty_int, "発注点": reorder_int,
        "最新入荷日": form_data["last_arrival"], "最新販売日": form_data["last_sale"],
        "消費期限": form_data["expiry"], "備考": form_data["note"],
    })
    return RedirectResponse(url="/inventory", status_code=303)
