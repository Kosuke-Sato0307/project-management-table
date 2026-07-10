#!/bin/sh
# 自己署名のTLS証明書を生成する。
# 使い方:
#   scripts/gen-cert.sh [出力先ディレクトリ] [ホスト名やIP(カンマ区切り・空白なし)]
# 例:
#   scripts/gen-cert.sh ./certs "localhost,192.168.1.10,pm-server"
set -e

CERT_DIR="${1:-./certs}"
HOSTS="${2:-localhost}"

mkdir -p "$CERT_DIR"

# subjectAltName（アクセスに使うホスト名/IPを証明書に登録する）を組み立てる
SAN=""
FIRST_HOST=""
OLD_IFS=$IFS
IFS=','
for h in $HOSTS; do
  [ -z "$FIRST_HOST" ] && FIRST_HOST="$h"
  # 数字とドットだけならIP、それ以外はDNS名として登録
  if echo "$h" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
    entry="IP:$h"
  else
    entry="DNS:$h"
  fi
  if [ -z "$SAN" ]; then SAN="$entry"; else SAN="$SAN,$entry"; fi
done
IFS=$OLD_IFS

echo "証明書を生成します (CN=$FIRST_HOST / SAN=$SAN)"
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$CERT_DIR/server.key" \
  -out "$CERT_DIR/server.crt" \
  -days 3650 \
  -subj "/CN=$FIRST_HOST" \
  -addext "subjectAltName=$SAN" >/dev/null 2>&1

chmod 600 "$CERT_DIR/server.key"
echo "生成しました: $CERT_DIR/server.crt , $CERT_DIR/server.key"
