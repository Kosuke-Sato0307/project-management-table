"""アプリの起動エントリポイント（gunicorn / flask コマンドが参照）。"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # 開発用の簡易起動（本番は gunicorn を使用）
    app.run(host="0.0.0.0", port=8000, debug=True)
