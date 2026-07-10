"""アプリ設定。環境変数から読み込む。"""
import os
from pathlib import Path

# プロジェクトのルートディレクトリ（このファイルの2つ上）
BASE_DIR = Path(__file__).resolve().parent.parent
# SQLite の DB ファイルは data/ に置く（Docker では Volume で永続化）
DATA_DIR = BASE_DIR / "data"


class Config:
    # セッション暗号化キー。本番では必ず .env で上書きすること。
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-key-change-me")

    # SQLite の接続先。環境変数 DATABASE_URL があれば優先（将来のPostgreSQL移行用）。
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 完全ローカル運用：外部にクッキーを送らない前提。HTTPのLAN運用も想定し既定はFalse。
    # HTTPS化した場合は .env で SESSION_COOKIE_SECURE=1 を設定。
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # アップロード（インポート用ファイル）の上限：10MB
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    # 表示タイムゾーン
    TIMEZONE = os.environ.get("TZ", "Asia/Tokyo")


class TestConfig(Config):
    """pytest 用：インメモリDBを使い、実データに影響を与えない。"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-key"
