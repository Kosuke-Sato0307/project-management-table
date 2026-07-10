#!/bin/sh
# コンテナ起動時の処理:
#   1) DBのマイグレーション（テーブル作成・更新）
#   2) マスタ（ステータス・確度ランク）の初期投入（既存があればスキップ）
#   3) Webサーバ（gunicorn）起動
set -e

echo "==> データベースをマイグレーションします..."
flask db upgrade

echo "==> マスタ初期値を投入します..."
flask seed-masters

echo "==> サーバを起動します (http://0.0.0.0:8000) ..."
exec gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 wsgi:app
