"""
SQLite データベース接続管理 + 初回 seed

【設計方針】
- DB ファイル: petlife-api/stock.db（リポジトリには含めない＝起動時に自動生成）
- 接続: 1リクエストごとに開いて閉じる contextmanager 方式
  → SQLite はファイルロックの仕様上、長期接続より都度接続のほうが安全
- 初回起動時、テーブルが空なら CSV から seed する
  → 2回目以降は CSV は読まない（DB が正）

【テーブル名・列名は英字】
  日本語 → 英字のマッピング（store.py で dict 変換時に元に戻す）:
    SKUコード → sku_code      商品名     → name
    カテゴリID → category_id   保管場所ID → location_id
    現在庫数   → qty           発注点     → reorder_point
    最新入荷日 → last_arrival  最新販売日 → last_sale
    消費期限   → expiry        備考       → note

【要発注フラグ】
  物理列にせず、SELECT 時に (qty < reorder_point) で計算する
  → 発注点や在庫数を変えるだけで連動するので不整合が出ない
"""

import sqlite3
import csv
from contextlib import contextmanager
from pathlib import Path


# =============================================================
# パス定数
# =============================================================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "stock.db"


# =============================================================
# スキーマ
# =============================================================
SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    sort_order  INTEGER NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS locations (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    sort_order  INTEGER NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS stock (
    sku_code        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category_id     INTEGER,
    location_id     INTEGER,
    qty             INTEGER NOT NULL DEFAULT 0,
    reorder_point   INTEGER NOT NULL DEFAULT 0,
    last_arrival    TEXT,
    last_sale       TEXT,
    expiry          TEXT,
    note            TEXT,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (location_id) REFERENCES locations(id)
);
"""


# =============================================================
# 接続管理
# =============================================================
@contextmanager
def get_conn():
    """SQLite 接続を1回ごとに作って閉じる。with 文で自動コミット/ロールバック。

    使い方:
        with get_conn() as conn:
            conn.execute("SELECT ...")
            # ブロックを抜けるときに COMMIT、例外時は ROLLBACK
    """
    # Python sqlite3 のデフォルト挙動を使う（DML 実行時に自動 BEGIN）
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# =============================================================
# 初回 seed
# =============================================================
def init_db() -> None:
    """テーブル作成 + 空ならCSVからseed。
    main.py の startup 時 or 初回 import 時に1回呼ぶ。
    """
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        if _is_empty(conn, "categories"):
            _seed_master(conn, "categories", BASE_DIR / "categories.csv")
        if _is_empty(conn, "locations"):
            _seed_master(conn, "locations", BASE_DIR / "locations.csv")
        if _is_empty(conn, "stock"):
            _seed_stock(conn, BASE_DIR / "stock.csv")


def _is_empty(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0] == 0


def _seed_master(conn: sqlite3.Connection, table: str, csv_path: Path) -> None:
    """カテゴリ・保管場所マスタの seed。
    CSV ヘッダー: id, name, sort_order, is_active
    """
    if not csv_path.exists():
        return
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        rows = [
            (
                int(row[0]),
                row[1].strip(),
                int(row[2]),
                1 if row[3].strip().lower() == "true" else 0,
            )
            for row in reader
            if any(cell.strip() for cell in row)
        ]
    conn.executemany(
        f"INSERT INTO {table} (id, name, sort_order, is_active) VALUES (?, ?, ?, ?)",
        rows,
    )


def _seed_stock(conn: sqlite3.Connection, csv_path: Path) -> None:
    """stock の seed。
    列順（CSV ヘッダー名は古いままでも列順は固定）:
      SKUコード, 商品名, カテゴリID, 保管場所ID, 現在庫数, 発注点,
      最新入荷日, 最新販売日, 消費期限, 備考
    """
    if not csv_path.exists():
        return
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        rows = []
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            rows.append((
                row[0].strip(),
                row[1].strip(),
                int(row[2]) if row[2].strip() else None,
                int(row[3]) if row[3].strip() else None,
                int(row[4]) if row[4].strip() else 0,
                int(row[5]) if row[5].strip() else 0,
                row[6].strip() or None,
                row[7].strip() or None,
                row[8].strip() or None,
                row[9].strip() or None,
            ))
    conn.executemany(
        """INSERT INTO stock (sku_code, name, category_id, location_id,
                              qty, reorder_point,
                              last_arrival, last_sale, expiry, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )


# =============================================================
# CLI 実行用（python db.py で seed 確認）
# =============================================================
if __name__ == "__main__":
    init_db()
    with get_conn() as conn:
        print(f"DB: {DB_PATH}")
        for table in ("categories", "locations", "stock"):
            cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table}: {cur.fetchone()[0]} rows")
