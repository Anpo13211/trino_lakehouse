-- tpch_iceberg_trino.sql
-- Purpose: Create TPCH tables in an Iceberg catalog (Trino) with types aligned to common TPCH Parquet distributions (DOUBLE for monetary/quantity fields).
-- Notes:
--   * Adjust paths and run ALTER TABLE ... EXECUTE add_files(...) separately to register existing Parquet.
--   * If you use Polaris vended credentials, place data under the Polaris warehouse bucket/prefix before add_files.
--   * Trino expects 's3://', not 's3a://'.

-- 0) Schema
CREATE SCHEMA IF NOT EXISTS iceberg.tpch;

-- 1) REGION
DROP TABLE IF EXISTS iceberg.tpch.region;
CREATE TABLE iceberg.tpch.region (
  r_regionkey BIGINT,
  r_name      VARCHAR,
  r_comment   VARCHAR
) WITH (format='PARQUET');

-- 2) NATION
DROP TABLE IF EXISTS iceberg.tpch.nation;
CREATE TABLE iceberg.tpch.nation (
  n_nationkey BIGINT,
  n_name      VARCHAR,
  n_regionkey BIGINT,
  n_comment   VARCHAR
) WITH (format='PARQUET');

-- 3) PART
DROP TABLE IF EXISTS iceberg.tpch.part;
CREATE TABLE iceberg.tpch.part (
  p_partkey     BIGINT,
  p_name        VARCHAR,
  p_mfgr        VARCHAR,
  p_brand       VARCHAR,
  p_type        VARCHAR,
  p_size        INTEGER,
  p_container   VARCHAR,
  p_retailprice DOUBLE,
  p_comment     VARCHAR
) WITH (format='PARQUET');

-- 4) SUPPLIER
DROP TABLE IF EXISTS iceberg.tpch.supplier;
CREATE TABLE iceberg.tpch.supplier (
  s_suppkey   BIGINT,
  s_name      VARCHAR,
  s_address   VARCHAR,
  s_nationkey BIGINT,
  s_phone     VARCHAR,
  s_acctbal   DOUBLE,
  s_comment   VARCHAR
) WITH (format='PARQUET');

-- 5) PARTSUPP
DROP TABLE IF EXISTS iceberg.tpch.partsupp;
CREATE TABLE iceberg.tpch.partsupp (
  ps_partkey    BIGINT,
  ps_suppkey    BIGINT,
  ps_availqty   INTEGER,
  ps_supplycost DOUBLE,
  ps_comment    VARCHAR
) WITH (format='PARQUET');

-- 6) CUSTOMER
DROP TABLE IF EXISTS iceberg.tpch.customer;
CREATE TABLE iceberg.tpch.customer (
  c_custkey     BIGINT,
  c_name        VARCHAR,
  c_address     VARCHAR,
  c_nationkey   BIGINT,
  c_phone       VARCHAR,
  c_acctbal     DOUBLE,
  c_mktsegment  VARCHAR,
  c_comment     VARCHAR
) WITH (format='PARQUET');

-- 7) ORDERS
DROP TABLE IF EXISTS iceberg.tpch.orders;
CREATE TABLE iceberg.tpch.orders (
  o_orderkey      BIGINT,
  o_custkey       BIGINT,
  o_orderstatus   VARCHAR,
  o_totalprice    DOUBLE,
  o_orderdate     DATE,
  o_orderpriority VARCHAR,
  o_clerk         VARCHAR,
  o_shippriority  INTEGER,
  o_comment       VARCHAR
) WITH (format='PARQUET');

-- 8) LINEITEM
DROP TABLE IF EXISTS iceberg.tpch.lineitem;
CREATE TABLE iceberg.tpch.lineitem (
  l_orderkey      BIGINT,
  l_partkey       BIGINT,
  l_suppkey       BIGINT,
  l_linenumber    INTEGER,
  l_quantity      BIGINT,        
  l_extendedprice DOUBLE,
  l_discount      DOUBLE,
  l_tax           DOUBLE,
  l_returnflag    VARCHAR,
  l_linestatus    VARCHAR,
  l_shipdate      VARCHAR,       
  l_commitdate    VARCHAR,       
  l_receiptdate   VARCHAR,       
  l_shipinstruct  VARCHAR,
  l_shipmode      VARCHAR,
  l_comment       VARCHAR
) WITH (format='PARQUET');


--
-- テーブルを作成後、以下のようなSQLを実行してデータを追加します。
-- ALTER TABLE iceberg.tpch.lineitem
--          -> EXECUTE add_files(
--          ->   location => 's3://warehouse/tpch/lineitem/', 
--          ->   format   => 'PARQUET'
--          -> );
--