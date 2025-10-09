このリポジトリは、Trino、Apache Iceberg、MinIOを使用したデータレイクハウス環境の研究用プロジェクトです。

## 構成

- **Trino**: 分散SQLクエリエンジン
- **Apache Iceberg**: テーブルフォーマット
- **Polaris**: Iceberg RESTカタログ
- **MinIO**: S3互換オブジェクトストレージ
- **TPC-H**: ベンチマークデータセット（SF1）

## ファイル構成

```
├── docker-compose.yml          # Docker Compose設定
├── utils/                      # ユーティリティスクリプト
│   ├── csv_to_parquet.py      # CSVからParquetへの変換スクリプト
│   └── upload_to_minio.py     # MinIOへのアップロードスクリプト
├── trino/                      # Trino設定ファイル
│   ├── catalog/
│   │   ├── iceberg.properties  # Icebergカタログ設定
│   │   └── tpch.properties     # TPC-Hカタログ設定
│   ├── config.properties       # Trino設定
│   ├── jvm.config             # JVM設定
│   ├── log.properties         # ログ設定
│   └── node.properties        # ノード設定
├── tpch_data/                  # TPC-Hデータセット
│   ├── csv/                    # CSV形式データ
│   ├── parquet/               # Parquet形式データ
│   └── dss.sql                # データベーススキーマ定義
└── zero-shot_datasets/         # Zero-Shotデータセット
    ├── accidents/              # 事故データセット
    ├── airline/                # 航空データセット
    ├── baseball/               # 野球データセット
    └── ...                     # その他のデータセット
```

## セットアップ手順

### 前提条件

- Docker と Docker Compose がインストールされていること
- 最低 8GB の RAM が利用可能であること

### 1. リポジトリのクローン

```bash
git clone https://github.com/Anpo13211/trino_lakehouse.git
cd trino_lakehouse
```

### 2. 環境の起動

```bash
docker-compose up -d
```

### 3. サービスの起動確認

```bash
# 全サービスの状態確認
docker-compose ps

# ログの確認（必要に応じて）
docker-compose logs -f
```

### 4. アクセストークンの取得とカタログ作成

```bash
# OAuth APIからアクセストークンを取得
ACCESS_TOKEN=$(curl -s -X POST \
  http://localhost:8181/api/catalog/v1/oauth/tokens \
  -d 'grant_type=client_credentials&client_id=root&client_secret=secret&scope=PRINCIPAL_ROLE:ALL' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")


# 念の為チェック
echo $ACCESS_TOKEN

# Polarisカタログを作成
curl -i -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8181/api/management/v1/catalogs \
  --json '{
    "name": "polariscatalog",
    "type": "INTERNAL",
    "properties": {
      "default-base-location": "s3://warehouse",
      "s3.endpoint": "http://minio:9000",
      "s3.path-style-access": "true",
      "s3.access-key-id": "admin",
      "s3.secret-access-key": "password",
      "s3.region": "dummy-region"
    },
    "storageConfigInfo": {
      "roleArn": "arn:aws:iam::000000000000:role/minio-polaris-role",
      "storageType": "S3",
      "allowedLocations": [
        "s3://warehouse/*"
      ]
    }
  }'
```

## サービスへのアクセス

- **Trino Web UI**: http://localhost:8080
- **MinIO Console**: http://localhost:9001 (admin/password)
- **MinIO API**: http://localhost:9000
- **Polaris API**: http://localhost:8181

## データの確認

```bash
# MinIOにアップロードされたファイルの確認
docker exec project-minio-client-1 mc ls minio/warehouse

# カタログの確認
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8181/api/management/v1/catalogs
```


## データセット

このプロジェクトには、Zero-Shotデータセットが含まれています：

### Zero-Shotデータセット
研究用のデータセットが `zero-shot_datasets/` ディレクトリに含まれています。

[DataManagementLab/zero-shot-cost-estimation](https://github.com/DataManagementLab/zero-shot-cost-estimation)(VLDB'22): 「Zero-Shot Cost Models for Out-of-the-box Learned Cost Prediction」で使用されたデータセットです。

#### データセット使用ルール
- **Scaledデータセットがある場合**: CSVデータは `scaled_<dataset>/` から、スキーマ・統計情報は `<dataset>/` から読み込み
- **Scaledデータセットがない場合**: すべて `<dataset>/` フォルダ内で完結

詳細は `zero-shot_datasets/DATASET_USAGE_ANNOTATION.md` を参照してください。

#### MinIO warehouseディレクトリの管理

```bash
# connection refused がでたら
# 必要があれば（MinIO コンテナに正常に接続するためのコマンド）
docker exec project-minio-client-1 mc alias set local

# Zero-shotデータセット用ディレクトリの作成
docker exec project-minio-client-1 mc mb local/warehouse/zero-shot

# 各データセット用ディレクトリの作成
docker exec project-minio-client-1 sh -c '
for dataset in accidents airline baseball basketball carcinogenesis consumer credit employee fhnk financial geneea genome hepatitis imdb imdb_full movielens seznam ssb tournament tpc_h walmart; do
  mc mb local/warehouse/zero-shot/$dataset
done
'

# ディレクトリ構造の確認
docker exec project-minio-client-1 mc ls local/warehouse/zero-shot/
```

## CSV to Parquet変換とアップロード

### 1. 仮想環境のセットアップ

```bash
# 仮想環境の作成とアクティベート
python3 -m venv venv
source venv/bin/activate

# 依存関係のインストール
pip install -r requirements.txt
```

### 2. CSV to Parquet変換

```bash
# 特定のデータセットをParquet形式に変換
python utils/csv_to_parquet.py <dataset_name>

# 例: Walmartデータセットを変換
python utils/csv_to_parquet.py walmart
```

**変換されるファイル:**
- CSVファイルが `zero-shot_datasets/<dataset>/parquet_data/` にParquet形式で保存される
- カラム統計情報 (`column_statistics.json`) に基づいて適切なデータ型が設定される

### 3. MinIOへのアップロード

```bash
# ParquetファイルをMinIOにアップロード
python utils/upload_to_minio.py

# MinIOの内容確認
docker exec project-minio-client-1 mc ls local/warehouse/zero-shot/<dataset>/
```

## Trinoでのテーブル操作

### Trinoへの接続

```bash
# Trinoコンテナに接続
docker exec -it project-trino-1 trino

# または、特定のカタログに直接接続
docker exec -it project-trino-1 trino --catalog iceberg
```

### テーブルの作成とデータ連携

#### 1. スキーマ（ネームスペース）の作成

```sql
-- Icebergカタログでスキーマを作成
CREATE SCHEMA IF NOT EXISTS iceberg.imdb;

-- 作成されたスキーマの確認
SHOW SCHEMAS IN iceberg;
```

#### 2. テーブルの作成（空のテーブル）

```sql
-- 使用するスキーマを指定
USE iceberg.imdb;

-- 空のテーブルを作成（例: nameテーブル）
CREATE TABLE IF NOT EXISTS name (
    id INTEGER,
    name VARCHAR,
    imdb_index VARCHAR,
    imdb_id DOUBLE,
    gender VARCHAR,
    name_pcode_cf VARCHAR,
    name_pcode_nf VARCHAR,
    surname_pcode VARCHAR,
    md5sum VARCHAR
);
-- MinIOに既にParquetファイルがアップロードされている場合、ALTER TABLEを使用してデータを連携させます：

sql
-- 既存のParquetファイルをテーブルに追加
ALTER TABLE iceberg.imdb.name
EXECUTE add_files(
  location => 's3a://warehouse/zero-shot/imdb/name/',
  format   => 'PARQUET'
);

-- ※: 注意
-- PARTITIONED が設定されたファイルではこの方法でやることができません（他の解決策を模索中）。
```

#### 1. テーブル一覧の確認

```sql
-- カタログ内の全スキーマを表示
SHOW SCHEMAS IN iceberg;

-- スキーマ内の全テーブルを表示
USE iceberg.imdb;
SHOW TABLES;
```

#### 2. テーブル構造、統計情報の確認

```sql
-- テーブルのカラム情報を表示
DESCRIBE name;

-- より詳細な情報を表示
SHOW COLUMNS FROM name;

-- テーブルの作成DDLを表示
SHOW CREATE TABLE name;

-- テーブルの統計情報を表示
SHOW STATS FOR name;
```

### テーブルの削除とトラブルシューティング

#### テーブルの削除

```sql
-- テーブルを削除（データも削除）
DROP TABLE IF EXISTS name;
```

#### トラブルシューティング

テーブルが破損している場合やメタデータに問題がある場合：

```bash
# 1. MinIOから直接データを削除
docker exec project-minio-client-1 mc rm --recursive --force minio/warehouse/zero-shot/imdb/name/

# 2. Trinoを再起動してメタデータキャッシュをクリア
docker-compose restart trino

# 3. テーブルを再作成
docker exec -it project-trino-1 trino
```

## 注意事項

- **データファイル**: TPC-HデータファイルはGitHubのサイズ制限により含まれていません。
- **メモリ使用量**: デフォルトで4GBのRAMが使用されます
- **ポート競合**: 8080, 8181, 9000, 9001, 5432ポートが使用されます

## ライセンス