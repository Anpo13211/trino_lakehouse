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
│   ├── csv_to_parquet.py                      # CSVからParquetへの変換
│   ├── upload_to_minio.py                     # MinIOへのアップロード
│   ├── generate_iceberg_ddl_from_parquet.py   # ParquetからIceberg DDL生成
│   ├── create_tables_and_link_parquet.py      # Trinoテーブル作成とParquetリンク
│   ├── create_schemas.py                      # Trinoスキーマ一括作成
│   └── convert_sql_to_iceberg.py              # PostgreSQL DDLをIceberg形式に変換
├── trino/                      # Trino設定ファイル
│   ├── catalog/
│   │   ├── iceberg.properties  # Icebergカタログ設定
│   │   └── tpch.properties     # TPC-Hカタログ設定
│   ├── config.properties       # Trino設定
│   ├── jvm.config             # JVM設定
│   ├── log.properties         # ログ設定
│   └── node.properties        # ノード設定
└── zero-shot_datasets/         # Zero-Shotデータセット
    ├── accidents/              
    ├── airline/                
    ├── baseball/               
    └── ...                     
```

## セットアップ手順

### 1. リポジトリのクローン

```bash
git clone https://github.com/ToyotaInfoTech/query-cost-prediction.git
cd query-cost-prediction
```

### 2. Zero-Shotデータセットのクローン

```bash
# Git LFSのインストール（初回のみ）
git lfs install

# Hugging Faceからzero-shot_datasetsリポジトリをクローン
git clone https://huggingface.co/datasets/Anpopo/zero-shot_datasets

# クローンしたディレクトリがtrino_lakehouse内に配置されていることを確認
ls zero-shot_datasets/
```

### 3. ネットワークとボリュームの作成

```bash
# Dockerネットワークの作成
docker network create local-iceberg-lakehouse

# Dockerボリュームの作成（trino-dataは自動作成されます）
docker volume create project_polaris-data
docker volume create project_minio-data
docker volume create project_postgres-data
```

### 4. 環境の起動

```bash
docker-compose up -d
```

### 5. サービスの起動確認

```bash
# 全サービスの状態確認
docker-compose ps

# ログの確認（必要に応じて）
docker-compose logs -f
```

### 6. アクセストークンの取得とカタログ作成

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

## データの確認（必要に応じて docker コンテナ名を変更）

```bash
# MinIOにアップロードされたファイルの確認
docker exec trino_lakehouse-minio-client-1 mc ls minio/warehouse

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
# Zero-shotデータセット用ディレクトリの作成
docker exec trino_lakehouse-minio-client-1 mc mb minio/warehouse/zero-shot

# 各データセット用ディレクトリの作成
docker exec trino_lakehouse-minio-client-1 sh -c '
for dataset in accidents airline baseball basketball carcinogenesis consumer credit employee fhnk financial geneea genome hepatitis imdb imdb_full movielens seznam ssb tournament tpc_h walmart; do
  mc mb local/warehouse/zero-shot/$dataset
done
'

# ディレクトリ構造の確認
docker exec trino_lakehouse-minio-client-1 mc ls local/warehouse/zero-shot/
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
# 特定のデータセットをアップロード
python utils/upload_to_minio.py walmart

# 全データセットを一括アップロード
python utils/upload_to_minio.py

# MinIOの内容確認
docker exec trino_lakehouse-minio-client-1 mc ls minio/warehouse/zero-shot/<dataset>/
```

**注意：`scaled_*`データセットの扱い**
- `scaled_*`ディレクトリのParquetファイルは、MinIOでは`scaled_`プレフィックスを除いた名前で保存されます
- 例：`python utils/upload_to_minio.py scaled_financial` → MinIOに`financial/`として保存

### 4. Iceberg DDLの生成

ParquetファイルからIceberg用のテーブル定義（DDL）を自動生成します：

```bash
# 特定のデータセットのDDLを生成
python utils/generate_iceberg_ddl_from_parquet.py walmart --with-schema

# 全データセットのDDLを一括生成
python utils/generate_iceberg_ddl_from_parquet.py --with-schema
```

**生成されるファイル:**
- `zero-shot_datasets/<dataset>/schema_sql/iceberg.sql`
- Parquetファイルの実際の型に基づいてDDLを生成
  - INT64 → BIGINT
  - STRING → VARCHAR
  - DOUBLE → DOUBLE
- SQL予約語（`order`など）は自動的に引用符で囲む

**`scaled_*`データセットの場合:**
- DDLは`scaled_`を除いたディレクトリに保存
- 例：`scaled_financial` → `zero-shot_datasets/financial/schema_sql/iceberg.sql`
- テーブル名も`iceberg.financial.*`になる

### 5. Trinoでテーブル作成とParquetファイルのリンク

生成したDDLを使ってTrinoでテーブルを作成し、MinIOのParquetファイルをリンクします：

```bash
# 特定のデータセットを処理
python utils/create_tables_and_link_parquet.py walmart

# 全データセットを一括処理
python utils/create_tables_and_link_parquet.py

# Linuxでsudoが必要な場合
python utils/create_tables_and_link_parquet.py walmart --sudo
python utils/create_tables_and_link_parquet.py --sudo
```

**処理内容:**
1. Icebergスキーマを自動作成（`iceberg.<dataset_name>`）
2. DDLファイルからテーブルを作成
3. MinIOのParquetファイルを`ALTER TABLE EXECUTE add_files`でリンク

**`scaled_*`データセットの動作:**
- `scaled_baseball`を指定 → `iceberg.baseball`スキーマに作成
- MinIOは`zero-shot/baseball/`を参照
- DDLは`zero-shot_datasets/baseball/schema_sql/iceberg.sql`を使用

### 完全なワークフロー例

```bash
# 例1: Walmartデータセット
python utils/csv_to_parquet.py walmart
python utils/upload_to_minio.py walmart
python utils/generate_iceberg_ddl_from_parquet.py walmart --with-schema
python utils/create_tables_and_link_parquet.py walmart

# 例2: Scaled Financialデータセット
python utils/csv_to_parquet.py scaled_financial
python utils/upload_to_minio.py scaled_financial
python utils/generate_iceberg_ddl_from_parquet.py scaled_financial --with-schema
python utils/create_tables_and_link_parquet.py scaled_financial

# 例3: 全データセットを一括処理
python utils/upload_to_minio.py
python utils/generate_iceberg_ddl_from_parquet.py --with-schema
python utils/create_tables_and_link_parquet.py
```

## Trinoでのテーブル操作

### Trinoへの接続

```bash
# Trinoコンテナに接続
docker exec -it trino_lakehouse-trino-1 trino

# または、特定のカタログに直接接続
docker exec -it trino_lakehouse-trino-1 trino --catalog iceberg
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

**テーブルのDROPが失敗する場合：**

```bash
# 1. MinIOからデータを削除
docker exec trino_lakehouse-minio-client-1 mc rm --recursive --force minio/warehouse/zero-shot/<dataset>/<table>/

# 2. Trinoを再起動
docker-compose restart trino

# 待機（起動完了まで）
sleep 20

# 3. 再度DROP
docker exec trino_lakehouse-trino-1 trino --execute 'DROP TABLE IF EXISTS iceberg.<dataset>.<table>;'
```

**スキーマごと削除する場合：**

```bash
# スキーマとすべてのテーブルを削除
docker exec trino_lakehouse-trino-1 trino --execute 'DROP SCHEMA IF EXISTS iceberg.<dataset> CASCADE;'

# MinIOのデータも削除
docker exec trino_lakehouse-minio-client-1 mc rm --recursive --force minio/warehouse/zero-shot/<dataset>/
```

**Icebergカタログを完全にリセット：**

```bash
# 全サービスを停止
docker-compose down

# Icebergメタデータを削除
docker volume rm project_postgres-data

# 再起動（カタログを再作成）
docker-compose up -d
```

## ユーティリティスクリプト詳細

### スクリプト一覧と使い分け

| スクリプト | 用途 | 引数 | オプション |
|-----------|------|------|-----------|
| `csv_to_parquet.py` | CSVをParquetに変換 | `<dataset>` または省略で全データセット | - |
| `upload_to_minio.py` | ParquetをMinIOにアップロード | `<dataset>` または省略で全データセット | - |
| `generate_iceberg_ddl_from_parquet.py` | ParquetスキーマからDDL生成 | `<dataset>` または省略で全データセット | `--with-schema` |
| `create_tables_and_link_parquet.py` | Trinoでテーブル作成＆リンク | `<dataset>` または省略で全データセット | `--sudo` |
| `create_schemas.py` | MinIOのデータセットからスキーマ作成 | - | `--sudo` |
| `convert_sql_to_iceberg.py` | PostgreSQL DDLをIceberg形式に変換 | `<dataset>` または省略で全データセット | `--with-schema` |

### データセット処理の推奨フロー

**通常のデータセット（walmart, tpc_h, imdbなど）:**
```bash
python utils/csv_to_parquet.py walmart
python utils/upload_to_minio.py walmart
python utils/generate_iceberg_ddl_from_parquet.py walmart --with-schema
python utils/create_tables_and_link_parquet.py walmart
```

**Scaled データセット（scaled_financial, scaled_baseballなど）:**
```bash
python utils/csv_to_parquet.py scaled_financial
python utils/upload_to_minio.py scaled_financial
python utils/generate_iceberg_ddl_from_parquet.py scaled_financial --with-schema
python utils/create_tables_and_link_parquet.py scaled_financial
```
※MinIO、Trino両方で`financial`（`scaled_`なし）として扱われます

**ボリューム管理コマンド：**

```bash
# ボリューム一覧確認
docker volume ls

# 特定ボリュームの詳細
docker volume inspect project_postgres-data

# Trinoキャッシュのクリア（安全）
docker-compose down
docker volume rm project_trino-data
docker-compose up -d
```

## 注意事項

- **データファイル**: TPC-HデータファイルはGitHubのサイズ制限により含まれていません。
- **メモリ使用量**: デフォルトで16GBのRAMが使用されます
- **ポート競合**: 8080, 8181, 9000, 9001, 5432ポートが使用されます
- **`scaled_*`データセット**: MinIOとTrinoでは`scaled_`プレフィックスなしで扱われます

## ライセンス
