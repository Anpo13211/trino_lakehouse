# Distributed Trino Setup

This setup deploys a distributed Trino cluster across multiple physical servers with the following configuration:

## Server Configuration

- **svr10** (192.168.8.80): Trino Coordinator
- **svr11** (192.168.8.90): Trino Worker
- **svr12** (192.168.8.100): Trino Worker
- **svr20** (192.168.8.140): Polaris Catalog + PostgreSQL
- **svr21** (192.168.8.150): MinIO

## Credentials

### MinIO
- Access Key: `admin`
- Secret Key: `password`
- Console URL: http://192.168.8.150:9001

### PostgreSQL
- Database: `polaris`
- User: `polaris`
- Password: `polaris`

### Polaris
- Realm: `default-realm`
- Principal: `root`
- Credentials: `secret`

## Memory Configuration

- Coordinator: 50GB+ memory
- Workers: 50GB+ memory each

## Network Configuration

**重要**: このセットアップは `network_mode: host` を使用しています。これにより：
- 各コンテナが物理サーバーのネットワークインターフェースを直接使用
- サーバー間でIPアドレス（192.168.8.x）を使って直接通信が可能
- ファイアウォール設定で以下のポートを開放する必要があります：
  - **Trino**: 8080 (全ノード)
  - **Polaris**: 8181, 5432
  - **MinIO**: 9000, 9001

## Prerequisites

各サーバーで以下が必要です：

1. **Docker & Docker Compose**: 最新版がインストールされていること
2. **SSH Access**: 各サーバー間でパスワードなしSSH接続が設定されていること
3. **Network Connectivity**: すべてのサーバーが互いに通信可能であること
4. **Firewall Configuration**: 必要なポートが開放されていること
5. **Memory**: 各Trinoノードで50GB以上のRAMが利用可能であること

### ファイアウォール設定例 (iptables)

```bash
# Trino port (all Trino nodes)
sudo iptables -A INPUT -p tcp --dport 8080 -j ACCEPT

# Polaris port (svr20)
sudo iptables -A INPUT -p tcp --dport 8181 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 5432 -j ACCEPT

# MinIO ports (svr21)
sudo iptables -A INPUT -p tcp --dport 9000 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 9001 -j ACCEPT
```

## Deployment

### 方法1: 自動デプロイ（推奨）

このリポジトリをすべてのサーバーに同期してから、deploy.shを実行します：

```bash
# スクリプトに実行権限を付与
chmod +x deploy.sh health-check.sh stop.sh

# デプロイを実行
./deploy.sh

# デプロイ後、ヘルスチェック実行
./health-check.sh
```

**注意**: deploy.shは各サーバーにSSH接続を行います。事前にパスワードなしSSH認証（SSH鍵）を設定しておいてください。

```bash
# SSH鍵の設定例（まだの場合）
ssh-keygen -t rsa -b 4096
ssh-copy-id user@192.168.8.80
ssh-copy-id user@192.168.8.90
ssh-copy-id user@192.168.8.100
ssh-copy-id user@192.168.8.140
ssh-copy-id user@192.168.8.150
```

### 方法2: 手動デプロイ

1. Copy the appropriate docker-compose files to each server:
   ```bash
   # svr10
   scp -r svr10-coordinator/ user@192.168.8.80:~/

   # svr11
   scp -r svr11-worker/ user@192.168.8.90:~/

   # svr12
   scp -r svr12-worker/ user@192.168.8.100:~/

   # svr20
   scp -r svr20-polaris/ user@192.168.8.140:~/

   # svr21
   scp -r svr21-minio/ user@192.168.8.150:~/
   ```

2. Verify network connectivity between servers:
   ```bash
   # From svr10, test connectivity to other servers
   ping 192.168.8.90
   ping 192.168.8.100
   ping 192.168.8.140
   ping 192.168.8.150
   ```

3. Deploy in the following order:
   - svr20: Polaris + PostgreSQL
   - svr21: MinIO
   - svr11, svr12: Trino Workers
   - svr10: Trino Coordinator

## Access

- Trino Web UI: http://192.168.8.80:8080
- MinIO Console: http://192.168.8.150:9001
- Polaris Catalog: http://192.168.8.140:8181

## Health Check and Testing

### 1. Verify Services Are Running

On each server, check Docker container status:
```bash
docker ps
docker logs <container-name>
```

### 2. Check Worker Registration

Access Trino Web UI at http://192.168.8.80:8080 and:
- Click on "Cluster" tab
- You should see 3 nodes total: 1 coordinator + 2 workers
- All nodes should show status "active"

Alternatively, use the Trino CLI:
```bash
docker exec -it trino-coordinator trino
```

Then run:
```sql
SELECT * FROM system.runtime.nodes;
```

Expected output:
```
node_id         | http_uri                    | node_version | coordinator | state
coordinator-01  | http://192.168.8.80:8080    | 458          | true        | active
worker-11       | http://192.168.8.90:8080    | 458          | false       | active
worker-12       | http://192.168.8.100:8080   | 458          | false       | active
```

### 3. Test Distributed Query Execution

```sql
-- Test query to verify distributed execution
EXPLAIN ANALYZE
SELECT nation, count(*) 
FROM tpch.tiny.customer 
GROUP BY nation;
```

Check the execution plan to confirm multiple workers are being used.

## Troubleshooting

### Workers Not Showing Up

1. Check network connectivity:
   ```bash
   # From coordinator server (svr10)
   telnet 192.168.8.90 8080
   telnet 192.168.8.100 8080
   ```

2. Check firewall settings - ensure port 8080 is open on all servers

3. Check worker logs:
   ```bash
   docker logs trino-worker-11
   docker logs trino-worker-12
   ```

4. Verify `discovery.uri` in config.properties points to correct coordinator IP

### Connection to Polaris/MinIO Failed

1. Verify services are running:
   ```bash
   curl http://192.168.8.140:8181/api/catalog/v1/config  # Polaris
   curl http://192.168.8.150:9000/minio/health/live      # MinIO
   ```

2. Check firewall settings for ports 8181 (Polaris) and 9000/9001 (MinIO)

3. Verify iceberg.properties has correct endpoints

## Distributed Query Execution

This setup supports:
- ✅ Parallel query execution across multiple workers
- ✅ Load balancing between workers
- ✅ Fault tolerance (if one worker fails, queries continue on others)
- ✅ Shared catalog access (Iceberg tables accessible from all nodes)
- ✅ Distributed joins and aggregations

## Configuration Summary

### Key Changes from Single-Node Setup

1. **Network Mode**: Changed from `bridge` to `host` to enable inter-server communication
2. **discovery.uri**: Set to coordinator's physical IP (192.168.8.80:8080)
3. **node.internal-address**: Set to each server's physical IP
4. **Unique node.id**: Each node has a unique identifier
5. **Distributed Execution Settings**: Added the following for optimal distributed query performance:
   - `distributed-joins-enabled=true` - Enable distributed hash joins
   - `distributed-sort=true` - Enable distributed sorting
   - `exchange.max-buffer-size=32MB` - Buffer size for data exchange between workers
   - `exchange.client-threads=25` - Threads for network communication
   - `query.remote-task.max-error-duration=5m` - Tolerance for transient network issues

### Distributed Query Optimization

このセットアップは以下の分散クエリ最適化を含んでいます：

1. **データ交換の最適化**
   - 32MBのバッファサイズでワーカー間のデータ転送を効率化
   - 25スレッドで並列にデータ交換を実行

2. **フォールトトレランス**
   - 5分間のエラー許容時間により、一時的なネットワーク問題に対応
   - ワーカーが一時的に利用できない場合でもクエリを継続

3. **分散実行の有効化**
   - 分散ハッシュジョイン：大規模なジョインを複数ワーカーに分散
   - 分散ソート：ソート処理を並列化

## デプロイ前チェックリスト

- [ ] すべてのサーバーでDockerとDocker Composeがインストール済み
- [ ] サーバー間でSSH接続が確立済み（パスワードなし）
- [ ] ネットワーク接続確認（pingテスト）
- [ ] 必要なポートがファイアウォールで開放済み
- [ ] 各Trinoノードで50GB以上のメモリが利用可能
- [ ] svr21でMinIO用のストレージ容量が十分
- [ ] svr20でPostgreSQL用のストレージ容量が十分

## デプロイ後チェックリスト

- [ ] すべてのDockerコンテナが起動している（`docker ps`）
- [ ] Trino Web UIでワーカーが登録されている（3ノード表示）
- [ ] MinIOコンソールにアクセス可能
- [ ] Polarisカタログが応答している
- [ ] テストクエリが正常に実行できる
- [ ] `SELECT * FROM system.runtime.nodes;` で全ノード表示

## なぜこの設定で分散連携が可能か

### 1. ネットワーク構成
- **`network_mode: host`**: 各コンテナがホストのネットワークを直接使用
  - これにより、192.168.8.x の物理IPアドレスで直接通信が可能
  - コンテナ間のネットワークブリッジやポートマッピングが不要

### 2. Discovery メカニズム
- **Coordinator** (svr10)が`discovery-server.enabled=true`でディスカバリーサーバーとして機能
- **Workers** (svr11, svr12)は`discovery.uri=http://192.168.8.80:8080`でコーディネーターに登録
- 各ワーカーは起動時に自動的にコーディネーターに接続し、クラスターに参加

### 3. ノード識別
- **node.id**: 各ノードに一意のID（coordinator-01, worker-11, worker-12）
- **node.internal-address**: 各ノードの物理IPアドレスを明示的に設定
  - Coordinator: 192.168.8.80
  - Worker-11: 192.168.8.90
  - Worker-12: 192.168.8.100

### 4. データ交換の最適化
- **exchange.max-buffer-size=32MB**: ワーカー間のデータ転送バッファ
- **exchange.client-threads=25**: 並列データ交換スレッド数
- **distributed-joins-enabled=true**: 分散ハッシュジョインを有効化

### 5. 共有ストレージとカタログ
- **MinIO** (svr21): すべてのノードから同じS3エンドポイント（192.168.8.150:9000）にアクセス
- **Polaris** (svr20): すべてのノードが同じカタログエンドポイント（192.168.8.140:8181）を参照
- これにより、すべてのノードが同じIcebergテーブルメタデータとデータにアクセス可能

## クラスターの動作フロー

```
1. ユーザー → Coordinator (192.168.8.80:8080) にクエリ送信
2. Coordinator がクエリを解析し、実行計画を作成
3. Coordinator が Worker-11 と Worker-12 にタスクを分散
4. 各 Worker が並列でデータを処理
   - MinIO (192.168.8.150) からデータを読み込み
   - Polaris (192.168.8.140) からメタデータを取得
5. Worker 間でデータ交換（必要な場合）
6. 各 Worker が結果を Coordinator に返送
7. Coordinator が最終結果を集約してユーザーに返す
```

## トラブルシューティング：よくある問題

### ワーカーがクラスターに参加しない

**症状**: Trino Web UIで2ノードしか表示されない（ワーカーが1つまたは0）

**解決方法**:
1. ワーカーノードのログを確認:
   ```bash
   ssh svr11 "docker logs trino-worker-11"
   ssh svr12 "docker logs trino-worker-12"
   ```
2. コーディネーターへの接続確認:
   ```bash
   ssh svr11 "curl http://192.168.8.80:8080/v1/info"
   ```
3. ファイアウォール設定を確認（ポート8080が開放されているか）

### クエリが1つのワーカーでしか実行されない

**症状**: EXPLAIN ANALYZEで確認すると、タスクが1つのワーカーに集中

**原因と解決**:
- データサイズが小さすぎる → `tpch.sf1`以上のスケールファクタを使用
- 分散設定が無効 → `config.properties`で`distributed-joins-enabled=true`を確認

### Iceberg/Polarisに接続できない

**症状**: `iceberg`カタログが使用できない

**解決方法**:
1. Polarisが起動しているか確認:
   ```bash
   ssh svr20 "docker ps | grep polaris"
   curl http://192.168.8.140:8181/api/catalog/v1/config
   ```
2. MinIOが起動しているか確認:
   ```bash
   ssh svr21 "docker ps | grep minio"
   curl http://192.168.8.150:9000/minio/health/live
   ```
