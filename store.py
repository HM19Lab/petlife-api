"""
データ層（在庫マスタ）

stock.csv をメモリ上の DataFrame として保持し、各エンドポイントから呼ばれる
取得・更新・追加・削除・絞り込み・ダッシュボード集計をすべてここで提供する。

【重要な前提】
- _df はモジュールグローバル。再代入する関数（add_to_df, delete_from_df）は
  必ず `global _df` を宣言してから書き換える
- ルーター側は _df を直接 import せず、本ファイルの関数経由でアクセスする
  （他モジュールから `from store import _df` すると、_df 再代入後にズレるため）
- 永続化はしない（デモ用）。再起動で stock.csv の初期値に戻る
"""

from datetime import date
import calendar
from pathlib import Path

from fastapi import HTTPException
import pandas as pd


# =============================================================
# CSV 読み込み
# =============================================================
BASE_DIR = Path(__file__).resolve().parent
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
# 取得系ヘルパー
# =============================================================
def get_all_stocks() -> list[dict]:
    """DataFrame を dict のリストに変換（テンプレート/JSON 両用）"""
    return _df.fillna("").to_dict(orient="records")


def get_stock_or_404(sku_code: str) -> dict:
    """1件取得。なければ404。テンプレート用のdictを返す。"""
    row = _df[_df["SKUコード"] == sku_code]
    if row.empty:
        raise HTTPException(
            status_code=404,
            detail=f"SKUコード '{sku_code}' が見つかりません",
        )
    return row.fillna("").to_dict(orient="records")[0]


def sku_exists(sku_code: str) -> bool:
    """指定SKUが既に登録されているかを返す（新規登録時の重複チェック用）"""
    return not _df[_df["SKUコード"] == sku_code].empty


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
        if category and item["カテゴリ"] != category:
            continue
        if keyword:
            target = (
                str(item["SKUコード"])
                + " " + str(item["商品名"])
                + " " + str(item["保管場所"])
            )
            if keyword not in target:
                continue
        if low_only and not item["要発注"]:
            continue
        results.append(item)
    return results


# =============================================================
# 更新・追加・削除
# =============================================================
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


# 詳細モーダルの「全フィールド更新」で書き換えてよい列のホワイトリスト。
# SKUコードはレコード識別子なので変更不可。要発注は他の列から自動計算。
EDITABLE_COLUMNS = {
    "商品名", "カテゴリ", "保管場所",
    "現在庫数", "発注点",
    "最新入荷日", "最新販売日", "消費期限", "備考",
}


def update_item_in_df(sku_code: str, fields: dict) -> dict:
    """指定SKUのレコードを複数フィールド一括で更新し、最新の1件(dict)を返す。

    詳細モーダルの「保存」ボタンから呼ばれる。update_qty_in_df の汎用版。

    - fields のうち EDITABLE_COLUMNS に含まれる列だけを反映する
      （知らない列名が混ざってきても無視 = 余計な列を増やさない安全弁）
    - 要発注フラグは現在庫数/発注点から自動再計算する
    - 該当SKUがなければ 404
    """
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
    return _df[mask].fillna("").to_dict(orient="records")[0]


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


def delete_from_df(sku_code: str) -> None:
    """指定SKUを DataFrame から削除する。なければ404。

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


# =============================================================
# ダッシュボード用 集計関数
# =============================================================
def _end_of_month(today: date) -> date:
    """当月末の日付を返す。例: 2026-05-24 → 2026-05-31"""
    last_day = calendar.monthrange(today.year, today.month)[1]
    return date(today.year, today.month, last_day)


def get_dashboard_stats(today: date | None = None) -> dict:
    """ダッシュボード用KPI 4枚分の数値を返す

    返り値の dict のキー:
      - total, low, expiring, categories, total_qty, today_iso, eom_iso
    """
    today = today or date.today()
    eom = _end_of_month(today)

    total = len(_df)
    low = int(_df["要発注"].sum())

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
    """カテゴリ別の商品数を集計（Chart.js 用、降順）"""
    counts = _df.groupby("カテゴリ").size().sort_values(ascending=False)
    return [{"label": k, "count": int(v)} for k, v in counts.items()]


def get_location_counts() -> list[dict]:
    """保管場所別の商品数を集計（Chart.js 用、降順）"""
    counts = _df.groupby("保管場所").size().sort_values(ascending=False)
    return [{"label": k, "count": int(v)} for k, v in counts.items()]
