"""
データ層（在庫 + カテゴリ・保管場所マスタ）

3つの CSV をメモリ上の DataFrame として保持する：
  - stock.csv       在庫データ
  - categories.csv  カテゴリマスタ
  - locations.csv   保管場所マスタ

すべてメモリ運用（永続化なし）。再起動で初期値に戻る。
次のステップで SQLite 移行予定。

【ID 設計】
  - stock.csv の「カテゴリ」「保管場所」列は ID 参照になっている（カテゴリID / 保管場所ID）
  - 画面表示や JSON API 応答では、ID から名前を引いた「カテゴリ」「保管場所」キーを
    付与する（_attach_master_names）。petlife-streamlit との互換性のため

【グローバル DF の扱い】
  - _df / _categories_df / _locations_df を再代入する関数は global 宣言が必須
  - ルーター側は import store した上で store.xxx() を呼ぶ
"""

from datetime import date
import calendar
from pathlib import Path

from fastapi import HTTPException
import pandas as pd


# =============================================================
# パス定数
# =============================================================
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "stock.csv"
CATEGORIES_CSV = BASE_DIR / "categories.csv"
LOCATIONS_CSV = BASE_DIR / "locations.csv"


# =============================================================
# stock.csv 読み込み
# =============================================================
COLUMNS = [
    "SKUコード", "商品名", "カテゴリID", "保管場所ID",
    "現在庫数", "発注点", "最新入荷日", "最新販売日", "消費期限", "備考",
]


def load_df() -> pd.DataFrame:
    """stock.csv を読み込んで整形した DataFrame を返す"""
    df = pd.read_csv(CSV_PATH, header=0)
    df.columns = COLUMNS
    # 数値列は欠損を 0 埋めしてから int 化
    df["現在庫数"] = pd.to_numeric(df["現在庫数"], errors="coerce").fillna(0).astype(int)
    df["発注点"] = pd.to_numeric(df["発注点"], errors="coerce").fillna(0).astype(int)
    # ID 列は欠損許容（pandas の Int64 = Nullable Int）
    df["カテゴリID"] = pd.to_numeric(df["カテゴリID"], errors="coerce").astype("Int64")
    df["保管場所ID"] = pd.to_numeric(df["保管場所ID"], errors="coerce").astype("Int64")
    df["要発注"] = df["現在庫数"] < df["発注点"]
    return df


# =============================================================
# マスタ読み込み（共通）
# =============================================================
MASTER_COLUMNS = ["id", "name", "sort_order", "is_active"]


def load_master(path: Path) -> pd.DataFrame:
    """カテゴリ・保管場所マスタ CSV を読み込む"""
    df = pd.read_csv(path, header=0)
    df["id"] = df["id"].astype(int)
    df["sort_order"] = df["sort_order"].astype(int)
    # is_active は CSV では "True" / "False" の文字列として入っている前提
    df["is_active"] = df["is_active"].astype(str).str.lower() == "true"
    return df


# メモリ上の DataFrame（再起動で初期値に戻る）
_df: pd.DataFrame = load_df()
_categories_df: pd.DataFrame = load_master(CATEGORIES_CSV)
_locations_df: pd.DataFrame = load_master(LOCATIONS_CSV)


# =============================================================
# マスタ取得（select 用 / CRUD 用）
# =============================================================
def _get_active(master_df: pd.DataFrame) -> list[dict]:
    """有効レコードのみ sort_order 順で返す（select 用）"""
    active = master_df[master_df["is_active"]].sort_values("sort_order")
    return active.to_dict(orient="records")


def _get_all_sorted(master_df: pd.DataFrame) -> list[dict]:
    """無効も含む全件を sort_order 順で返す（CRUD 画面用）"""
    return master_df.sort_values("sort_order").to_dict(orient="records")


def get_active_categories() -> list[dict]:
    return _get_active(_categories_df)


def get_active_locations() -> list[dict]:
    return _get_active(_locations_df)


def get_all_categories() -> list[dict]:
    return _get_all_sorted(_categories_df)


def get_all_locations() -> list[dict]:
    return _get_all_sorted(_locations_df)


# =============================================================
# ID → 名前 ルックアップ
# =============================================================
def _name_by_id(master_df: pd.DataFrame, id_) -> str:
    """ID から name を引く。見つからない/NaN は空文字"""
    if id_ is None or pd.isna(id_):
        return ""
    row = master_df[master_df["id"] == int(id_)]
    return str(row.iloc[0]["name"]) if not row.empty else ""


def get_category_name(id_) -> str:
    return _name_by_id(_categories_df, id_)


def get_location_name(id_) -> str:
    return _name_by_id(_locations_df, id_)


def category_id_exists(id_: int) -> bool:
    return not _categories_df[_categories_df["id"] == int(id_)].empty


def location_id_exists(id_: int) -> bool:
    return not _locations_df[_locations_df["id"] == int(id_)].empty


# =============================================================
# マスタ CRUD（カテゴリ・保管場所 共通の内部関数）
# =============================================================
def _next_id(master_df: pd.DataFrame) -> int:
    """次に振る ID = 既存最大 + 1。空なら 1"""
    if master_df.empty:
        return 1
    return int(master_df["id"].max()) + 1


def _add_master(kind: str, name: str, sort_order: int | None, is_active: bool) -> dict:
    """共通 add。kind = 'categories' or 'locations'

    sort_order の扱い：
      - None（空欄）: 既存の sort_order 最大 + 1（末尾追加）
      - 既存と重複: sort_order >= N の行を全部 +1 してから新行を N に（シフト方式）
    """
    global _categories_df, _locations_df
    # .copy() で元 DataFrame を直接書き換えないようにする（途中失敗時の安全策）
    target = (_categories_df if kind == "categories" else _locations_df).copy()
    new_id = _next_id(target)

    if sort_order is None:
        # 空欄なら末尾。空マスタなら 1 から
        sort_order = int(target["sort_order"].max()) + 1 if not target.empty else 1
    else:
        # 重複していたら N 以降を 1 ずつ後ろにシフト
        if (target["sort_order"] == sort_order).any():
            shift_mask = target["sort_order"] >= sort_order
            target.loc[shift_mask, "sort_order"] += 1

    new_row = {"id": new_id, "name": name, "sort_order": int(sort_order), "is_active": bool(is_active)}
    new_df = pd.concat([target, pd.DataFrame([new_row])], ignore_index=True)
    if kind == "categories":
        _categories_df = new_df
    else:
        _locations_df = new_df
    return new_row


def _update_master(kind: str, id_: int, name: str, sort_order: int, is_active: bool) -> dict:
    """共通 update。kind = 'categories' or 'locations'

    sort_order の扱い：
      - 自分以外で sort_order=N と重複していたら、他の行をシフト（+1）
      - 自分自身の sort_order を N に確定
    """
    global _categories_df, _locations_df
    target = (_categories_df if kind == "categories" else _locations_df).copy()
    mask = target["id"] == id_
    if not mask.any():
        raise HTTPException(status_code=404, detail=f"ID '{id_}' が見つかりません")

    other_mask = ~mask  # 自分以外の行
    # 自分以外で N と重複していたら、N 以降の他の行を +1
    if ((target["sort_order"] == sort_order) & other_mask).any():
        shift_mask = (target["sort_order"] >= sort_order) & other_mask
        target.loc[shift_mask, "sort_order"] += 1

    target.loc[mask, "name"] = name
    target.loc[mask, "sort_order"] = int(sort_order)
    target.loc[mask, "is_active"] = bool(is_active)

    if kind == "categories":
        _categories_df = target
    else:
        _locations_df = target
    return target[mask].to_dict(orient="records")[0]


def _delete_master(kind: str, id_: int) -> None:
    """共通 delete。使用中チェックはルーター側で行うこと"""
    global _categories_df, _locations_df
    target = _categories_df if kind == "categories" else _locations_df
    if target[target["id"] == id_].empty:
        raise HTTPException(status_code=404, detail=f"ID '{id_}' が見つかりません")
    new_df = target[target["id"] != id_].reset_index(drop=True)
    if kind == "categories":
        _categories_df = new_df
    else:
        _locations_df = new_df


# 公開ラッパー（カテゴリ）
def add_category(name: str, sort_order: int | None = None, is_active: bool = True) -> dict:
    return _add_master("categories", name, sort_order, is_active)


def update_category(id_: int, name: str, sort_order: int, is_active: bool) -> dict:
    return _update_master("categories", id_, name, sort_order, is_active)


def delete_category(id_: int) -> None:
    _delete_master("categories", id_)


# 公開ラッパー（保管場所）
def add_location(name: str, sort_order: int | None = None, is_active: bool = True) -> dict:
    return _add_master("locations", name, sort_order, is_active)


def update_location(id_: int, name: str, sort_order: int, is_active: bool) -> dict:
    return _update_master("locations", id_, name, sort_order, is_active)


def delete_location(id_: int) -> None:
    _delete_master("locations", id_)


# =============================================================
# 使用中チェック（削除前のブロック判定用）
# =============================================================
def count_category_usage(id_: int) -> int:
    """指定カテゴリIDを使っている stock の件数（0 なら未使用 = 削除可）"""
    return int((_df["カテゴリID"] == id_).sum())


def count_location_usage(id_: int) -> int:
    """指定保管場所IDを使っている stock の件数（0 なら未使用 = 削除可）"""
    return int((_df["保管場所ID"] == id_).sum())


# =============================================================
# 在庫データ取得
# =============================================================
def _attach_master_names(records: list[dict]) -> list[dict]:
    """各レコードに「カテゴリ」「保管場所」（名前）を join する。
    テンプレート表示用 + petlife-streamlit 互換のため。
    """
    for r in records:
        r["カテゴリ"] = get_category_name(r.get("カテゴリID"))
        r["保管場所"] = get_location_name(r.get("保管場所ID"))
    return records


def get_all_stocks() -> list[dict]:
    """DataFrame を dict のリストに変換。マスタ名も付与"""
    records = _df.fillna("").to_dict(orient="records")
    return _attach_master_names(records)


def get_stock_or_404(sku_code: str) -> dict:
    """1件取得。マスタ名付き"""
    row = _df[_df["SKUコード"] == sku_code]
    if row.empty:
        raise HTTPException(
            status_code=404,
            detail=f"SKUコード '{sku_code}' が見つかりません",
        )
    record = row.fillna("").to_dict(orient="records")[0]
    _attach_master_names([record])
    return record


def sku_exists(sku_code: str) -> bool:
    """新規登録時の重複チェック用"""
    return not _df[_df["SKUコード"] == sku_code].empty


def filter_stocks(category_id: str, keyword: str, low_only: bool) -> list[dict]:
    """検索条件で在庫を絞り込む

    - category_id: 文字列で受け取り、空文字なら絞り込みなし
    - keyword:     SKUコード/商品名/保管場所名のいずれかに部分一致
    - low_only:    True なら 要発注 のみ
    """
    cat_filter: int | None = None
    s = str(category_id).strip()
    if s != "":
        try:
            cat_filter = int(s)
        except ValueError:
            cat_filter = None

    results = []
    for item in get_all_stocks():
        if cat_filter is not None and item.get("カテゴリID") != cat_filter:
            continue
        if keyword:
            target = (
                str(item["SKUコード"])
                + " " + str(item["商品名"])
                + " " + str(item.get("保管場所", ""))
            )
            if keyword not in target:
                continue
        if low_only and not item["要発注"]:
            continue
        results.append(item)
    return results


# =============================================================
# 在庫の更新・追加・削除
# =============================================================
def update_qty_in_df(sku_code: str, qty: int) -> dict:
    """指定SKUの現在庫数を更新し、最新の1件 dict を返す。
    要発注フラグも連動で再計算する。
    """
    global _df
    if _df[_df["SKUコード"] == sku_code].empty:
        raise HTTPException(
            status_code=404,
            detail=f"SKUコード '{sku_code}' が見つかりません",
        )
    _df.loc[_df["SKUコード"] == sku_code, "現在庫数"] = qty
    _df["要発注"] = _df["現在庫数"] < _df["発注点"]
    record = _df[_df["SKUコード"] == sku_code].fillna("").to_dict(orient="records")[0]
    _attach_master_names([record])
    return record


# 詳細モーダル「全フィールド更新」で書き換えてよい列。SKUコードは識別子なので不可。
EDITABLE_COLUMNS = {
    "商品名", "カテゴリID", "保管場所ID",
    "現在庫数", "発注点",
    "最新入荷日", "最新販売日", "消費期限", "備考",
}


def update_item_in_df(sku_code: str, fields: dict) -> dict:
    """複数フィールド一括更新。EDITABLE_COLUMNS にある列のみ反映する。"""
    global _df
    if _df[_df["SKUコード"] == sku_code].empty:
        raise HTTPException(
            status_code=404,
            detail=f"SKUコード '{sku_code}' が見つかりません",
        )
    mask = _df["SKUコード"] == sku_code
    for col, value in fields.items():
        if col in EDITABLE_COLUMNS:
            _df.loc[mask, col] = value
    _df["要発注"] = _df["現在庫数"] < _df["発注点"]
    record = _df[mask].fillna("").to_dict(orient="records")[0]
    _attach_master_names([record])
    return record


def add_to_df(new_row: dict) -> None:
    """新しい商品を追加する。要発注フラグは全行再計算。"""
    global _df
    _df = pd.concat([_df, pd.DataFrame([new_row])], ignore_index=True)
    # ID 列の型を維持（concat で object に落ちることがあるため）
    _df["カテゴリID"] = pd.to_numeric(_df["カテゴリID"], errors="coerce").astype("Int64")
    _df["保管場所ID"] = pd.to_numeric(_df["保管場所ID"], errors="coerce").astype("Int64")
    _df["要発注"] = _df["現在庫数"] < _df["発注点"]


def delete_from_df(sku_code: str) -> None:
    """指定SKUを削除する。なければ 404"""
    global _df
    if _df[_df["SKUコード"] == sku_code].empty:
        raise HTTPException(
            status_code=404,
            detail=f"SKUコード '{sku_code}' が見つかりません",
        )
    _df = _df[_df["SKUコード"] != sku_code].reset_index(drop=True)


# =============================================================
# ダッシュボード集計
# =============================================================
def _end_of_month(today: date) -> date:
    last_day = calendar.monthrange(today.year, today.month)[1]
    return date(today.year, today.month, last_day)


def get_dashboard_stats(today: date | None = None) -> dict:
    """KPI 用の集計値"""
    today = today or date.today()
    eom = _end_of_month(today)

    total = len(_df)
    low = int(_df["要発注"].sum())

    exp = pd.to_datetime(_df["消費期限"], errors="coerce")
    today_ts = pd.Timestamp(today)
    eom_ts = pd.Timestamp(eom)
    expiring = int(((exp >= today_ts) & (exp <= eom_ts)).sum())

    # カテゴリ数 = stock に出現するカテゴリのユニーク数（マスタ全件数ではない）
    categories = int(_df["カテゴリID"].nunique())
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
    """カテゴリ別の商品数（Chart.js 用、降順）"""
    counts = _df.groupby("カテゴリID").size().sort_values(ascending=False)
    return [{"label": get_category_name(k), "count": int(v)} for k, v in counts.items()]


def get_location_counts() -> list[dict]:
    """保管場所別の商品数（Chart.js 用、降順）"""
    counts = _df.groupby("保管場所ID").size().sort_values(ascending=False)
    return [{"label": get_location_name(k), "count": int(v)} for k, v in counts.items()]
