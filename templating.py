"""
Jinja2 テンプレートの共通インスタンス

main.py と routers/ の両方から同じ Jinja2Templates を使いたいので、
独立した小モジュールに切り出してある（main.py に置くと循環importになる）。
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
