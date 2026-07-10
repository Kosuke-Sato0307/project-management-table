"""アプリケーションファクトリ。

create_app() で Flask アプリを組み立てる。テスト時は設定を差し替えられる。
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path

from flask import Flask
from flask_wtf.csrf import CSRFProtect

from .config import Config, DATA_DIR
from .extensions import db, migrate, login_manager

csrf = CSRFProtect()


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    # data/ ディレクトリを確実に用意（SQLite ファイル置き場）
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

    # 拡張の初期化
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # モデルをインポートしておく（マイグレーションに認識させるため）
    from . import models  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(models.User, user_id)

    # Blueprint 登録
    from .auth.routes import auth_bp
    from .admin.routes import admin_bp
    from .main.routes import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(main_bp)

    # CLI コマンド（初期管理者作成・マスタ初期投入）
    from .cli import register_cli
    register_cli(app)

    # テンプレートで使うフィルタ/関数
    _register_template_helpers(app)

    return app


def _register_template_helpers(app: Flask) -> None:
    tz_offset = timedelta(hours=9)  # Asia/Tokyo (JST)

    @app.template_filter("jst")
    def jst(value):
        """UTCで保存した日時をJST表示に変換。"""
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return (value.astimezone(timezone(tz_offset))).strftime("%Y-%m-%d %H:%M")

    @app.template_filter("yen")
    def yen(value):
        """金額を 1,234,567 円 形式で表示。"""
        if value is None or value == "":
            return ""
        try:
            return f"{int(value):,}"
        except (ValueError, TypeError):
            return str(value)

    @app.template_filter("ymd")
    def ymd(value):
        """日付を YYYY-MM-DD 表示。"""
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else str(value)
