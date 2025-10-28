# 分散Trinoセットアップ - セットアップノート

このドキュメントは、シングルノード設定（`docker-compose.yml`）と分散環境設定の相違点と、設定の根拠をまとめたものです。

## シングルノード設定からの変更点

### 1. ネットワークモード

**シングルノード**:
```yaml
networks:
  - local-iceberg-lakehouse
```

**分散環境**:
```yaml
network_mode: host
```

**理由**: 複数の物理サーバー間で通信するため、各コンテナがホストのネットワークインターフェースを直接使用する必要がある。

### 2. Polaris設定の統一

**シングルノードの設定を採用**:
- 完全な環境変数セット
- `polaris-admin-bootstrap`による初期化
- PostgreSQLヘルスチェックの追加
- Polarisヘルスチェックの追加

**追加された環境変数**:
```yaml
AWS_ACCESS_KEY_ID: admin
AWS_SECRET_ACCESS_KEY: password
AWS_REGION: dummy-region
AWS_ENDPOINT_URL_S3: http://192.168.8.150:9000  # 分散環境では物理IP
POLARIS_BOOTSTRAP_CREDENTIALS: default-realm,root,secret
polaris.features.DROP_WITH_PURGE_ENABLED: "true"
polaris.realm-context.realms: default-realm
```

### 3. MinIO設定の統一

**シングルノードの設定を採用**:
- `minio-client`による自動バケット作成
- 統一された認証情報（admin/password）

**追加されたサービス**:
```yaml
minio-client:
  image: minio/mc:latest
  entrypoint: >
    /bin/sh -c "
    until (mc alias set minio http://localhost:9000 admin password) do echo '...waiting...' && sleep 1; done;
    mc mb minio/warehouse || true;
    mc anonymous set public minio/warehouse;
    echo 'MinIO setup completed!';
    tail -f /dev/null
    "
```

### 4. 認証情報の統一

**変更前**:
- MinIO: minioadmin/minioadmin
- PostgreSQL: polaris/polaris123

**変更後**:
- MinIO: admin/password
- PostgreSQL: polaris/polaris
- Polaris: root/secret (default-realm)

これにより、シングルノード環境と分散環境で同じ認証情報を使用できます。

## 分散環境特有の設定

### エンドポイントの設定

シングルノードでは`minio`や`postgres`のようなDockerネットワーク上のホスト名を使用しますが、分散環境では物理IPアドレスを使用します。

**シングルノード**:
```yaml
AWS_ENDPOINT_URL_S3: http://minio:9000
QUARKUS_DATASOURCE_JDBC_URL: jdbc:postgresql://postgres:5432/polaris
```

**分散環境**:
```yaml
AWS_ENDPOINT_URL_S3: http://192.168.8.150:9000
QUARKUS_DATASOURCE_JDBC_URL: jdbc:postgresql://localhost:5432/polaris
```

注: 分散環境では`network_mode: host`を使用しているため、同一サーバー内のサービスは`localhost`でアクセスします。

## デプロイ順序の重要性

1. **PostgreSQL** (svr20) - 最初に起動
2. **polaris-admin-bootstrap** (svr20) - PostgreSQLが健全になった後、自動的に実行されスキーマを作成
3. **Polaris Catalog** (svr20) - ブートストラップ完了後に起動
4. **MinIO + minio-client** (svr21) - 並行して起動可能
5. **Trino Workers** (svr11, svr12) - Polarisが準備できてから
6. **Trino Coordinator** (svr10) - 最後に起動

`deploy.sh`スクリプトはこの順序を自動的に実行します。

## トラブルシューティング

### Polarisが起動しない

**チェック項目**:
1. PostgreSQLが正常に起動しているか
   ```bash
   ssh svr20 "docker logs polaris-postgres"
   ```
2. polaris-admin-bootstrapが正常に完了したか
   ```bash
   ssh svr20 "docker logs polaris-admin-bootstrap"
   ```
3. Polarisカタログのログを確認
   ```bash
   ssh svr20 "docker logs polaris-catalog"
   ```

### MinIOのwarehouseバケットが作成されない

**チェック項目**:
1. minio-clientのログを確認
   ```bash
   ssh svr21 "docker logs minio-client"
   ```
2. 手動でバケットを作成
   ```bash
   ssh svr21 "docker exec -it minio-client mc mb minio/warehouse"
   ```

### Trinoからicebergカタログが見えない

**チェック項目**:
1. Polarisが正常に起動しているか
   ```bash
   curl http://192.168.8.140:8181/healthcheck
   ```
2. MinIOが正常に起動しているか
   ```bash
   curl http://192.168.8.150:9000/minio/health/live
   ```
3. Trinoの設定が正しいか
   ```bash
   ssh svr10 "docker exec -it trino-coordinator cat /etc/trino/catalog/iceberg.properties"
   ```

## 設定のベストプラクティス

1. **認証情報の一貫性**: すべてのコンポーネントで同じ認証情報を使用
2. **ヘルスチェックの活用**: `depends_on`で`condition: service_healthy`を使用
3. **自動初期化**: ブートストラップスクリプトでセットアップを自動化
4. **ログの確認**: 問題が発生した場合は必ずログを確認

## 参考リンク

- [Apache Polaris Documentation](https://polaris.apache.org/)
- [Trino Documentation](https://trino.io/docs/current/)
- [MinIO Documentation](https://min.io/docs/minio/linux/index.html)


