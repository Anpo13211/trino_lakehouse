-- Test queries for distributed Trino setup
-- これらのクエリで分散実行が正しく動作していることを確認できます

-- ============================================
-- 1. クラスター状態確認
-- ============================================

-- 1.1 ノード一覧表示（3ノード：1コーディネーター + 2ワーカー）
SELECT 
    node_id,
    http_uri,
    node_version,
    coordinator,
    state
FROM system.runtime.nodes
ORDER BY coordinator DESC, node_id;

-- 1.2 クラスターメモリ使用状況
SELECT 
    node_id,
    pool_id,
    reserved_bytes / 1024.0 / 1024.0 / 1024.0 as reserved_gb,
    max_bytes / 1024.0 / 1024.0 / 1024.0 as max_gb
FROM system.runtime.memory_pools
ORDER BY node_id, pool_id;

-- ============================================
-- 2. 基本接続テスト
-- ============================================

-- 2.1 シンプルなクエリ
SELECT 'Hello from distributed Trino!' as message;

-- 2.2 TPC-H connector テスト
SELECT count(*) as total_customers FROM tpch.tiny.customer;

-- ============================================
-- 3. 分散実行テスト
-- ============================================

-- 3.1 Memory connectorでテストテーブル作成
CREATE SCHEMA IF NOT EXISTS memory.test;

DROP TABLE IF EXISTS memory.test.distributed_test;

CREATE TABLE memory.test.distributed_test AS
SELECT 
    n.nationkey,
    n.name as nation_name,
    c.custkey,
    c.name as customer_name,
    c.acctbal
FROM tpch.tiny.nation n
CROSS JOIN tpch.tiny.customer c;

-- 3.2 分散集計テスト
SELECT 
    nation_name,
    count(*) as customer_count,
    avg(acctbal) as avg_balance,
    sum(acctbal) as total_balance
FROM memory.test.distributed_test
GROUP BY nation_name
ORDER BY total_balance DESC;

-- 3.3 分散ジョインテスト（EXPLAIN ANALYZEで確認）
EXPLAIN ANALYZE
SELECT 
    c.custkey,
    c.name,
    count(o.orderkey) as order_count,
    sum(o.totalprice) as total_spent
FROM tpch.tiny.customer c
LEFT JOIN tpch.tiny.orders o ON c.custkey = o.custkey
GROUP BY c.custkey, c.name
HAVING count(o.orderkey) > 10
ORDER BY total_spent DESC
LIMIT 20;

-- 3.4 複雑な分散クエリ（複数ジョインとウィンドウ関数）
EXPLAIN ANALYZE
SELECT 
    n.name as nation,
    r.name as region,
    c.name as customer,
    o.orderdate,
    o.totalprice,
    ROW_NUMBER() OVER (PARTITION BY n.nationkey ORDER BY o.totalprice DESC) as rank_in_nation
FROM tpch.tiny.nation n
JOIN tpch.tiny.region r ON n.regionkey = r.regionkey
JOIN tpch.tiny.customer c ON c.nationkey = n.nationkey
JOIN tpch.tiny.orders o ON o.custkey = c.custkey
WHERE o.totalprice > 100000
ORDER BY n.name, rank_in_nation
LIMIT 50;

-- ============================================
-- 4. パフォーマンステスト
-- ============================================

-- 4.1 大規模集計（ワーカー間でデータが分散されるべき）
EXPLAIN ANALYZE
SELECT 
    l.orderkey,
    sum(l.quantity) as total_quantity,
    sum(l.extendedprice) as total_price,
    avg(l.discount) as avg_discount,
    count(DISTINCT l.partkey) as distinct_parts
FROM tpch.sf1.lineitem l
GROUP BY l.orderkey
HAVING sum(l.quantity) > 100
ORDER BY total_price DESC
LIMIT 100;

-- 4.2 分散ソートテスト
EXPLAIN ANALYZE
SELECT 
    c.custkey,
    c.name,
    c.nationkey,
    c.acctbal,
    ROW_NUMBER() OVER (ORDER BY c.acctbal DESC) as wealth_rank
FROM tpch.sf1.customer c
ORDER BY wealth_rank
LIMIT 1000;

-- ============================================
-- 5. Icebergカタログテスト（設定済みの場合）
-- ============================================

-- 5.1 Icebergスキーマ一覧
-- SHOW SCHEMAS FROM iceberg;

-- 5.2 Icebergテーブル作成テスト
-- CREATE SCHEMA IF NOT EXISTS iceberg.test_schema;
-- CREATE TABLE IF NOT EXISTS iceberg.test_schema.sample_table (
--     id BIGINT,
--     name VARCHAR,
--     created_at TIMESTAMP
-- ) WITH (format = 'PARQUET');

-- 5.3 Icebergテーブルへのデータ挿入
-- INSERT INTO iceberg.test_schema.sample_table
-- SELECT 
--     custkey as id,
--     name,
--     current_timestamp as created_at
-- FROM tpch.tiny.customer
-- LIMIT 100;

-- ============================================
-- 6. モニタリングクエリ
-- ============================================

-- 6.1 実行中のクエリ
SELECT 
    query_id,
    state,
    query_type,
    user,
    source,
    query,
    created as start_time,
    elapsed_time
FROM system.runtime.queries 
WHERE state IN ('RUNNING', 'QUEUED')
ORDER BY created DESC;

-- 6.2 最近完了したクエリ
SELECT 
    query_id,
    state,
    query_type,
    elapsed_time,
    execution_time,
    planning_time,
    query
FROM system.runtime.queries 
WHERE state IN ('FINISHED', 'FAILED')
ORDER BY created DESC
LIMIT 10;

-- 6.3 クエリ統計（最後のクエリ）
SELECT 
    node_id,
    task_id,
    stage_id,
    state,
    input_rows,
    input_bytes / 1024.0 / 1024.0 as input_mb,
    output_rows,
    output_bytes / 1024.0 / 1024.0 as output_mb
FROM system.runtime.tasks
WHERE query_id = (SELECT query_id FROM system.runtime.queries ORDER BY created DESC LIMIT 1)
ORDER BY stage_id, task_id;

-- ============================================
-- 7. ワーカー負荷分散確認
-- ============================================

-- このクエリでタスクがワーカー間でどう分散されているか確認
SELECT 
    node_id,
    count(*) as task_count,
    sum(input_rows) as total_input_rows,
    sum(output_rows) as total_output_rows,
    sum(input_bytes) / 1024.0 / 1024.0 as total_input_mb,
    sum(output_bytes) / 1024.0 / 1024.0 as total_output_mb
FROM system.runtime.tasks
WHERE state IN ('RUNNING', 'FINISHED')
GROUP BY node_id
ORDER BY node_id;
