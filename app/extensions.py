"""Flask拡張のインスタンスをここで生成し、app factory から初期化する。

循環インポートを避けるため、拡張はモデル/アプリ本体とは別ファイルに置く。
"""
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

# 未ログイン時に飛ばすログイン画面のエンドポイント名
login_manager.login_view = "auth.login"
login_manager.login_message = "ログインが必要です。"
login_manager.login_message_category = "warning"
