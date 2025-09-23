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
├── tpch_csv/                   # TPC-H CSVデータ
└── tpch_parquet/              # TPC-H Parquetデータ
```

## 使用方法

### 1. 環境の起動

```bash
docker-compose up -d
```

### 2. サービスへのアクセス

- **Trino Web UI**: http://localhost:8080
- **MinIO Console**: http://localhost:9001 (admin/password)
- **MinIO API**: http://localhost:9000

### 3. Trinoへの接続

```bash
docker exec trino_research-trino-1 trino
```

### 4. カタログの確認

```sql
SHOW CATALOGS;
SHOW SCHEMAS FROM iceberg;
```

## データセット

このプロジェクトには、TPC-HベンチマークのSF1（Scale Factor 1）データセットが含まれています：

- **CSV形式**: `tpch_csv/` ディレクトリ
- **Parquet形式**: `tpch_parquet/` ディレクトリ

## 注意事項

- Polarisのカタログは永続化されていないため、コンテナ再起動時に再作成が必要です
- メモリ使用量に注意してください（JVM設定: 1GB）

## ライセンス

このプロジェクトは研究目的で作成されています。