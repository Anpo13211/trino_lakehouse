# Trino Research with Iceberg and MinIO

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
├── trino/                      # Trino設定ファイル
│   ├── catalog/
│   │   ├── iceberg.properties  # Icebergカタログ設定
│   │   └── tpch.properties     # TPC-Hカタログ設定
│   ├── config.properties       # Trino設定
│   ├── jvm.config             # JVM設定
│   ├── log.properties         # ログ設定
│   └── node.properties        # ノード設定
└── tpch_data/                  # TPC-Hデータセット
    ├── csv/                    # CSV形式データ
    ├── parquet/               # Parquet形式データ
    └── dss.sql                # データベーススキーマ定義
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

### 5. データのアップロード（オプション）

```bash
# parquetファイルをMinIOにアップロード
docker cp tpch_data/parquet/customer.parquet project-minio-client-1:/tmp/
docker exec project-minio-client-1 mc cp /tmp/customer.parquet minio/warehouse/

docker cp tpch_data/parquet/orders.parquet project-minio-client-1:/tmp/
docker exec project-minio-client-1 mc cp /tmp/orders.parquet minio/warehouse/

docker cp tpch_data/parquet/lineitem.parquet project-minio-client-1:/tmp/
docker exec project-minio-client-1 mc cp /tmp/lineitem.parquet minio/warehouse/
...
```

## サービスへのアクセス

- **Trino Web UI**: http://localhost:8080
- **MinIO Console**: http://localhost:9001 (admin/password)
- **MinIO API**: http://localhost:9000
- **Polaris API**: http://localhost:8181

## 使用方法

### Trinoへの接続

```bash
docker exec project-trino-1 trino
```

### カタログの確認

```sql
SHOW CATALOGS;
SHOW SCHEMAS FROM iceberg;
```

### データの確認

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
機械学習研究用のデータセットが `zero-shot_datasets/` ディレクトリに含まれています。

このデータセットは、[DataManagementLab/zero-shot-cost-estimation](https://github.com/DataManagementLab/zero-shot-cost-estimation)プロジェクトのVLDB'22論文「Zero-Shot Cost Models for Out-of-the-box Learned Cost Prediction」で使用されたデータセットです。

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

# データセットファイルのアップロード例
docker cp zero-shot_datasets/baseball/players.csv project-minio-client-1:/tmp/
docker exec project-minio-client-1 mc cp /tmp/players.csv local/warehouse/zero-shot/baseball/
```

## 永続化について

このセットアップでは以下のデータが永続化されます：

- **MinIOデータ**: `minio-data` ボリュームに保存
- **Polarisカタログ**: PostgreSQLデータベースに保存
- **PostgreSQLデータ**: `postgres-data` ボリュームに保存

Docker Composeを再起動しても、データとカタログは保持されます。

## トラブルシューティング

### サービスが起動しない場合

```bash
# ログを確認
docker-compose logs [service-name]

# サービスを再起動
docker-compose restart [service-name]

# 完全にクリーンアップして再起動
docker-compose down -v
docker-compose up -d
```

### メモリ不足の場合

`docker-compose.yml`の`TRINO_JVM_OPTS`を調整してください：

```yaml
environment:
  - TRINO_JVM_OPTS=-Xmx2G  # 2GBに減らす
```

## 注意事項

- **データファイル**: TPC-HデータファイルはGitHubのサイズ制限により含まれていません。別途取得してください
- **メモリ使用量**: デフォルトで4GBのRAMが使用されます
- **ポート競合**: 8080, 8181, 9000, 9001, 5432ポートが使用されます

## ライセンス

このプロジェクトは研究目的で作成されています。