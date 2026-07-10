#!/bin/sh
# コンテナ起動時の処理:
#   1) TLS証明書が無ければ自己署名で自動生成（すぐHTTPSで動くように）
#   2) DBのマイグレーション（テーブル作成・更新）
#   3) マスタ（ステータス・確度ランク）の初期投入（既存があればスキップ）
#   4) Webサーバ（gunicorn / HTTPS）起動
set -e

CERT_DIR=/app/certs
CERT_FILE="$CERT_DIR/server.crt"
KEY_FILE="$CERT_DIR/server.key"

if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
  echo "==> TLS証明書が見つかりません。自己署名証明書を自動生成します..."
  echo "    （警告を消したい場合は、後から certs/ に社内CA発行の証明書を置き換えてください）"
  /app/scripts/gen-cert.sh "$CERT_DIR" "${CERT_HOSTS:-localhost}"
fi

echo "==> データベースをマイグレーションします..."
flask db upgrade

echo "==> マスタ初期値を投入します..."
flask seed-masters

echo "==> サーバを起動します (https://0.0.0.0:8000) ..."
exec gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 \
  --certfile "$CERT_FILE" --keyfile "$KEY_FILE" \
  wsgi:app
