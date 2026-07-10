# 案件管理システム（社内・完全ローカル運用）

案件情報を管理するデータベースとWeb画面です。**インターネットには一切公開せず、社内のPC/サーバ上だけ**で動かすことを前提にしています。

- **通信はHTTPS（暗号化）**。パスワード等が平文で流れないようにしています。
- ログイン制（ID／パスワード）。ユーザーは管理者が事前登録します。
- 案件の検索・閲覧・編集・エクスポート／インポートができます（順次追加中）。
- データは1つのファイル（SQLite）に保存され、そのファイルをコピーするだけでバックアップできます。

> **現在の実装状況**: フェーズ1（基盤＋ログイン／ユーザー管理）まで完成。
> 案件の一覧・検索・登録・編集、エクスポート（CSV/Excel/PDF）、インポート（Excel/CSV）は次フェーズ以降で追加します。

---

> **Windowsで初めて動かす方へ**: 画面つきの詳しい手順は
> [`docs/はじめかた_Windows.md`](docs/はじめかた_Windows.md) を参照してください。

## 1. 動かすのに必要なもの

- **Docker Desktop**（Windows / Mac）または **Docker Engine**（Linux）
  - これ1つ入れれば、Python等を個別にインストールする必要はありません。

## 2. セットアップ手順（初回のみ）

### ① 設定ファイルを作る
プロジェクトのフォルダで、サンプルをコピーして `.env` を作ります。

```bash
cp .env.example .env
```

`.env` を開き、次の2点を設定してください。

- `SECRET_KEY` … **推測されない長い文字列**に変更（生成例: `python -c "import secrets; print(secrets.token_hex(32))"`）
- `CERT_HOSTS` … このサーバに**アクセスするときのアドレス**を入れる（HTTPS証明書に登録されます）
  - 例: 社内の他PCからサーバ(IP 192.168.1.10)にアクセスするなら `CERT_HOSTS=localhost,192.168.1.10`

### ② 起動する

```bash
docker compose up -d --build
```

初回起動時に、自動で以下が行われます。
- **HTTPS用の証明書を自動生成**（自己署名。`CERT_HOSTS` の値を登録）
- データベースのテーブル作成
- 案件ステータス（進行中／受注／失注／完了）・確度ランク（A／B／C）の初期値投入

### ③ 最初の管理者アカウントを作る
起動中のコンテナ内で、対話形式で管理者を作成します。

```bash
docker compose exec web flask create-admin
```

ログインID・氏名・パスワードを聞かれるので入力してください。

### ④ ブラウザでアクセス

```
https://localhost
```

作成した管理者でログインできます。
社内の**別のPC**からアクセスさせる場合は、サーバPCのIPアドレスを使います（例: `https://192.168.1.10`）。
（`HTTPS_PORT` を443以外にした場合は `https://<サーバ>:<ポート>` の形になります）

> **初回に「この接続ではプライバシーが保護されません」等の警告が出ます。**
> 自己署名証明書のためで、社内LAN内の利用であれば「詳細設定 →〈このサイトにアクセスする〉」で進めて問題ありません。
> 警告を消したい場合は下記「HTTPS（証明書）について」を参照してください。

## 3. 使い方（管理者）

1. 管理者でログイン → 上部メニュー「ユーザー管理」
2. 「＋ ユーザーを登録」でログインID・氏名・権限を入力
3. 登録すると**初期パスワードが1度だけ画面に表示**されます。本人に伝えてください。
4. 各利用者は初回ログイン時にパスワード変更を求められます。
5. パスワードを忘れた場合は、管理者が「PWリセット」で再発行できます。

- **権限**: 「一般」は案件の閲覧・編集が可能。「管理者」はそれに加えてユーザー管理が可能です。

## 4. バックアップ

データは `data/app.db`（SQLiteファイル）に入っています。
**このファイルをコピーするだけ**でバックアップになります。定期的に別の場所へコピーしてください。

```bash
# 例: 日付つきでコピー
cp data/app.db backups/app_$(date +%Y%m%d).db
```

## 5. 停止・再起動

```bash
docker compose down      # 停止
docker compose up -d     # 起動
```

## 6. HTTPS（証明書）について

本システムはHTTPSで通信します。証明書の運用は2通りあります。

### A. 自己署名証明書（既定・すぐ使える）
初回起動時に自動生成されます。設定不要ですぐHTTPSになりますが、ブラウザに警告が出ます。
社内LAN内であれば、警告画面で「このサイトにアクセスする」を選べば利用できます。

- アクセスに使うIP/ホスト名を変えたときは、証明書を作り直してください（`certs/` の中身を消して再起動すれば自動再生成、または下記スクリプト）。

```bash
# 例: サーバIPを登録して作り直す
docker compose exec web sh /app/scripts/gen-cert.sh /app/certs "localhost,192.168.1.10"
docker compose restart web
```

### B. 警告を出さない（社内で信頼される証明書を使う）
各PCに「信頼するCA証明書」を1回インストールする方法です。おすすめは **mkcert**（無料）です。

1. サーバ管理者のPCで mkcert を使い、ローカルCAと、サーバのIP/ホスト名向けの証明書を発行
2. 発行された証明書・鍵を `certs/server.crt` `certs/server.key` として配置し `docker compose restart web`
3. mkcert のローカルCA（`mkcert -CAROOT` にある rootCA.pem）を、アクセスする各PCに「信頼されたルート証明機関」としてインストール

これで警告なしのHTTPSになります。社内に独自の認証局(CA)がある場合は、そのCA発行の証明書を `certs/` に置いても構いません。

## 7. セキュリティ上の注意

- **インターネットに公開しないでください。** 社内LAN内でのみ利用します。
- ルーターのポート開放（ポートフォワーディング）はしないでください。
- 通信はHTTPSで暗号化されます（証明書は上記のとおり運用してください）。
- 初期パスワードは必ず本人に変更させてください。
- 管理者アカウントの管理に注意してください。
- `certs/` 内の秘密鍵（server.key）や `.env` は共有・コミットしないでください。

---

## 開発者向け情報

### ローカル（Docker無し）で動かす

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export FLASK_APP=wsgi.py          # Windows(PowerShell): $env:FLASK_APP="wsgi.py"
flask db upgrade                  # テーブル作成
flask seed-masters                # マスタ初期値
flask create-admin                # 管理者作成
flask run --host 0.0.0.0 --port 8000    # 開発用。この起動はHTTP（本番はDockerでHTTPS）
```

> 開発用の `flask run` はHTTPです（手元での動作確認用）。本番運用はDocker（HTTPS）を使ってください。

### テスト

```bash
pytest
```

### 項目（カラム）を追加したいとき（拡張）

1. `app/models.py` にカラムを追加
2. マイグレーションを生成して適用

```bash
flask db migrate -m "add xxx column"
flask db upgrade
```

（Docker運用中は次回起動時に `flask db upgrade` が自動実行されます）

### 選択肢（ステータス・確度ランク）を増やしたいとき

将来のマスタ管理画面、または `app/cli.py` の `seed-masters` を参考に追加できます。

### 構成

```
app/
├─ __init__.py     アプリ生成（app factory）
├─ config.py       設定
├─ extensions.py   DB/ログイン等の拡張
├─ models.py       テーブル定義（User / Project / Status / Rank）
├─ cli.py          管理者作成・マスタ投入コマンド
├─ decorators.py   権限チェック
├─ auth/           ログイン・パスワード変更
├─ admin/          ユーザー管理
├─ main/           ホーム
├─ templates/      画面（HTML）
└─ static/         CSS（外部CDNは使わず同梱）
migrations/        DBマイグレーション（Alembic）
tests/             自動テスト
data/              SQLite DB本体（バックアップ対象）
```
