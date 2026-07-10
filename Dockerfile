# 案件管理システム: アプリ用Dockerイメージ
FROM python:3.12-slim

# 日本語ロケール/タイムゾーンの基本設定
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Tokyo

WORKDIR /app

# 自己署名証明書の自動生成に openssl を使う
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

# 依存を先に入れてキャッシュを効かせる
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリ本体
COPY . .

# 起動スクリプト（マイグレーション → マスタ投入 → サーバ起動）
RUN chmod +x /app/entrypoint.sh /app/scripts/gen-cert.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
