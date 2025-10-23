#!/usr/bin/env python3
"""
EXPLAIN ANALYZE実行スクリプト

各データセットのワークロードクエリに対してEXPLAIN ANALYZEを実行し、
結果をファイルに保存するスクリプトです。
"""

import os
import sys
import time
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any
import argparse
from datetime import datetime
from tqdm import tqdm

# Trino接続設定
TRINO_HOST = "localhost"
TRINO_PORT = "8080"
TRINO_USER = "admin"
TRINO_CATALOG = "iceberg"
TRINO_SCHEMA = "default"

class TrinoClient:
    """Trinoクライアント"""
    
    def __init__(self, host: str, port: str, user: str, catalog: str, schema: str, use_sudo: bool = False):
        self.host = host
        self.port = port
        self.user = user
        self.catalog = catalog
        self.schema = schema
        self.base_url = f"http://{host}:{port}"
        self.use_sudo = use_sudo
        self.trino_container = self._find_trino_container()
    
    def _find_trino_container(self) -> str:
        """Trinoコンテナ名を自動検出"""
        try:
            # 1. trinodb/trinoイメージのコンテナを検索
            docker_cmd = ["sudo", "docker"] if self.use_sudo else ["docker"]
            result = subprocess.run(
                docker_cmd + ["ps", "--filter", "ancestor=trinodb/trino", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                container_name = result.stdout.strip().split('\n')[0]
                print(f"Found Trino container: {container_name}")
                return container_name
            
            # 2. 名前パターンマッチングで検索（優先順位付き）
            all_containers_result = subprocess.run(
                docker_cmd + ["ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if all_containers_result.returncode == 0:
                container_names = all_containers_result.stdout.strip().split('\n')
                
                # 優先順位付きパターンマッチング（より具体的なパターンを優先）
                priority_patterns = [
                    ("trino_lakehouse-trino-", "trino_で始まりtrinoで終わる"),  # 最優先
                    ("trino-trino-", "trino-trino-パターン"),
                    ("trino_", "trino_で始まる"),
                    ("trino-", "trino-で始まる"),
                    ("-trino-", "-trino-を含む"),
                    ("_trino_", "_trino_を含む")
                ]
                
                # 優先順位順に検索
                for pattern, description in priority_patterns:
                    for container_name in container_names:
                        if pattern in container_name:
                            # さらに具体的なチェック：実際にTrinoコンテナかどうかを確認
                            if self._is_trino_container(container_name):
                                print(f"Found Trino container by pattern '{pattern}' ({description}): {container_name}")
                                return container_name
            
            # 3. フォールバック: 一般的なコンテナ名を試す
            fallback_names = [
                "trino_lakehouse-trino-1",  # 実際のコンテナ名を最優先に
                "lakehouse-trino-1", 
                "trino", 
                "trino-1",
                "trino-lakehouse-1"
            ]
            for name in fallback_names:
                try:
                    # コンテナが存在するかチェック
                    check_result = subprocess.run(
                        docker_cmd + ["inspect", name],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if check_result.returncode == 0:
                        print(f"Using fallback Trino container: {name}")
                        return name
                except:
                    continue
            
            print("Warning: Could not find Trino container, using default: trino_lakehouse-trino-1")
            return "trino_lakehouse-trino-1"
        except Exception as e:
            print(f"Warning: Error detecting Trino container: {e}, using default: trino_lakehouse-trino-1")
            return "trino_lakehouse-trino-1"
    
    def _is_trino_container(self, container_name: str) -> bool:
        """指定されたコンテナが実際にTrinoコンテナかどうかを確認"""
        try:
            # コンテナのイメージを確認
            docker_cmd = ["sudo", "docker"] if self.use_sudo else ["docker"]
            result = subprocess.run(
                docker_cmd + ["inspect", container_name, "--format", "{{.Config.Image}}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                image_name = result.stdout.strip()
                # trinodb/trinoイメージかどうかを確認
                if "trinodb/trino" in image_name:
                    return True
            
            # コンテナ内にtrinoコマンドがあるかチェック
            check_trino_result = subprocess.run(
                docker_cmd + ["exec", container_name, "which", "trino"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if check_trino_result.returncode == 0:
                return True
                
            return False
        except:
            return False
    
    def execute_query(self, query: str) -> Dict[str, Any]:
        """クエリを実行して結果を返す"""
        try:
            # Dockerコンテナ内のtrino-cliを使用してクエリを実行
            docker_cmd = ["sudo", "docker"] if self.use_sudo else ["docker"]
            cmd = docker_cmd + [
                "exec", self.trino_container, "trino",
                "--catalog", self.catalog,
                "--schema", self.schema,
                "--execute", query
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30  # 30秒のタイムアウト
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Query timeout (5 minutes)",
                "returncode": -1
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1
            }
    
    def get_available_schemas(self) -> List[str]:
        """利用可能なスキーマのリストを取得"""
        try:
            docker_cmd = ["sudo", "docker"] if self.use_sudo else ["docker"]
            cmd = docker_cmd + [
                "exec", self.trino_container, "trino",
                "--catalog", self.catalog,
                "--execute", "SHOW SCHEMAS;"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                # スキーマ名を抽出（引用符を除去）
                schemas = []
                for line in result.stdout.strip().split('\n'):
                    line = line.strip()
                    if line and not line.startswith('"information_schema"') and not line.startswith('"system"'):
                        # 引用符を除去
                        schema_name = line.strip('"')
                        schemas.append(schema_name)
                return sorted(schemas)
            else:
                print(f"Error getting schemas: {result.stderr}")
                return []
        except Exception as e:
            print(f"Error getting schemas: {e}")
            return []

class WorkloadAnalyzer:
    """ワークロード分析器"""
    
    def __init__(self, workloads_dir: str, output_dir: str, trino_client: TrinoClient):
        self.workloads_dir = Path(workloads_dir)
        self.output_dir = Path(output_dir)
        self.trino_client = trino_client
        
        # 出力ディレクトリを作成（相対パスを使用）
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            # 相対パスで再試行
            self.output_dir = Path("./explain_analyze_results")
            self.output_dir.mkdir(parents=True, exist_ok=True)
            print(f"Using relative path for output directory: {self.output_dir}")
        except Exception as e:
            print(f"Error creating output directory: {e}")
            # 現在のディレクトリに作成
            self.output_dir = Path("./explain_analyze_results")
            self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def get_datasets(self) -> List[str]:
        """利用可能なデータセットのリストを取得（Trino環境とワークロードディレクトリの両方を確認）"""
        # Trino環境で利用可能なスキーマを取得
        available_schemas = self.trino_client.get_available_schemas()
        print(f"Available schemas in Trino: {len(available_schemas)}")
        
        # ワークロードディレクトリから利用可能なデータセットを取得
        if not self.workloads_dir.exists():
            raise FileNotFoundError(f"Workloads directory not found: {self.workloads_dir}")
        
        workload_datasets = []
        for item in self.workloads_dir.iterdir():
            if item.is_dir():
                workload_datasets.append(item.name)
        
        # 両方に存在するデータセットのみを返す
        common_datasets = []
        for schema in available_schemas:
            if schema in workload_datasets:
                common_datasets.append(schema)
        
        print(f"Common datasets (both in Trino and workloads): {len(common_datasets)}")
        return sorted(common_datasets)
    
    def get_workload_files(self, dataset: str) -> List[Path]:
        """指定されたデータセットのワークロードファイルを取得"""
        dataset_dir = self.workloads_dir / dataset
        if not dataset_dir.exists():
            return []
        
        workload_files = []
        for file in dataset_dir.glob("*.sql"):
            workload_files.append(file)
        
        return sorted(workload_files)
    
    def read_queries_from_file(self, file_path: Path) -> List[str]:
        """SQLファイルからクエリを読み込む"""
        queries = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 各行が1つのクエリと仮定
                for line in content.strip().split('\n'):
                    line = line.strip()
                    if line and not line.startswith('--'):
                        queries.append(line)
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
        
        return queries
    
    def execute_explain_analyze(self, query: str, dataset: str, workload_file: str, query_index: int) -> Dict[str, Any]:
        """EXPLAIN ANALYZEを実行（タイムアウト付き）"""
        explain_query = f"EXPLAIN ANALYZE {query}"
        
        # データセット名をスキーマとして使用
        original_schema = self.trino_client.schema
        self.trino_client.schema = dataset
        
        start_time = time.time()
        
        # タイムアウトはTrinoClient内で設定済み（30秒）
        
        result = self.trino_client.execute_query(explain_query)
        execution_time = time.time() - start_time
        
        # スキーマを元に戻す
        self.trino_client.schema = original_schema
        
        return {
            "dataset": dataset,
            "workload_file": workload_file,
            "query_index": query_index,
            "original_query": query,
            "explain_query": explain_query,
            "execution_time": execution_time,
            "timestamp": datetime.now().isoformat(),
            "result": result
        }
    
    def save_results(self, results: List[Dict[str, Any]], dataset: str, workload_file: str):
        """結果をファイルに保存（成功したクエリプランのみを連続して保存）"""
        if not results:
            print(f"No successful queries to save for {dataset}")
            return
            
        output_file = self.output_dir / f"{dataset}_{workload_file}_explain_analyze.txt"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for i, result in enumerate(results):
                    # クエリのヘッダーを追加
                    f.write(f"-- {workload_file} stmt {i + 1}\n")
                    
                    # 成功したクエリプランの生の出力をそのまま保存
                    stdout = result["result"]["stdout"]
                    f.write(stdout)
                    f.write("\n\n")
            
            print(f"Results saved to: {output_file}")
        except Exception as e:
            print(f"Error saving results to {output_file}: {e}")
    
    def analyze_dataset(self, dataset: str, max_queries: int = 10000):
        """指定されたデータセットを分析（デフォルトで10000個のクエリプランを収集）"""
        print(f"\n=== Analyzing dataset: {dataset} ===")
        
        workload_files = self.get_workload_files(dataset)
        if not workload_files:
            print(f"No workload files found for dataset: {dataset}")
            return
        
        # complex_workload_200k_s1.sqlファイルからクエリを取得
        complex_workload_file = None
        for workload_file in workload_files:
            if "complex_workload_200k_s1.sql" in workload_file.name:
                complex_workload_file = workload_file
                break
        
        if not complex_workload_file:
            print("complex_workload_200k_s1.sql not found")
            return
        
        print(f"Processing workload file: {complex_workload_file.name}")
        queries = self.read_queries_from_file(complex_workload_file)
        if not queries:
            print(f"No queries found in {complex_workload_file.name}")
            return
        
        print(f"Total queries available: {len(queries)}")
        
        results = []
        
        # tqdmを使用して進捗表示（成功したクエリのみカウント）
        successful_queries = 0
        with tqdm(total=max_queries, desc=f"Processing {dataset}", unit="query") as pbar:
            for i, query in enumerate(queries):
                try:
                    result = self.execute_explain_analyze(
                        query, dataset, complex_workload_file.name, i
                    )
                    
                    # 成功したクエリのみを保存し、進捗に反映
                    if result["result"]["success"]:
                        execution_time = result["execution_time"]
                        
                        # 実行時間のフィルタリング（100ms - 30000ms）
                        if 0.1 <= execution_time <= 30.0:
                            results.append(result)
                            successful_queries += 1
                            pbar.set_postfix({"status": "✓"})
                            pbar.update(1)
                            
                            # 必要な数のクエリが成功したら終了
                            if successful_queries >= max_queries:
                                break
                        else:
                            # 実行時間が範囲外のクエリは無視
                            pbar.set_postfix({"status": "timeout"})
                    else:
                        # 失敗したクエリは無視（進捗も更新しない）
                        error_msg = result["result"]["stderr"][:50] + "..." if len(result["result"]["stderr"]) > 50 else result["result"]["stderr"]
                        pbar.set_postfix({"status": "failed"})
                    
                    # クエリ間の待機時間（サーバー負荷軽減）
                    time.sleep(0.05)
                    
                except Exception as e:
                    # エラーが発生したクエリも無視
                    pbar.set_postfix({"status": "error"})
                    continue
        
        # 結果を保存
        self.save_results(results, dataset, "complex_workload_200k_s1")
        
        # 成功したクエリの統計を表示
        print(f"  Results: {successful_queries} successful queries collected from {len(queries)} total queries")
    
    def analyze_all_datasets(self, max_queries: int = 10000):
        """すべてのデータセットを分析"""
        datasets = self.get_datasets()
        print(f"Found {len(datasets)} datasets: {', '.join(datasets)}")
        
        # 全体の進捗表示
        with tqdm(total=len(datasets), desc="Processing datasets", unit="dataset") as dataset_pbar:
            for dataset in datasets:
                try:
                    self.analyze_dataset(dataset, max_queries)
                    dataset_pbar.set_postfix({"current": dataset})
                except Exception as e:
                    print(f"Error analyzing dataset {dataset}: {e}")
                    dataset_pbar.set_postfix({"current": dataset, "status": "✗"})
                    continue
                dataset_pbar.update(1)

def main():
    parser = argparse.ArgumentParser(description="Execute EXPLAIN ANALYZE on workload queries")
    parser.add_argument("--workloads-dir", default="./zero-shot_datasets/workloads",
                       help="Directory containing workload files")
    parser.add_argument("--output-dir", default="./explain_analyze_results",
                       help="Directory to save results")
    parser.add_argument("--dataset", help="Specific dataset to analyze (optional)")
    parser.add_argument("--max-queries", type=int, default=10000, help="Maximum number of queries per workload file (default: 10000)")
    parser.add_argument("--trino-host", default="localhost", help="Trino host")
    parser.add_argument("--trino-port", default="8080", help="Trino port")
    parser.add_argument("--trino-user", default="admin", help="Trino user")
    parser.add_argument("--trino-catalog", default="iceberg", help="Trino catalog")
    parser.add_argument("--trino-schema", default="default", help="Trino schema")
    parser.add_argument("--sudo", action="store_true", help="Use sudo for Docker commands")
    
    args = parser.parse_args()
    
    # パスを絶対パスに変換（エラーハンドリング付き）
    try:
        workloads_dir = Path(args.workloads_dir).resolve()
        output_dir = Path(args.output_dir).resolve()
        
        # 出力ディレクトリを作成
        output_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        print(f"Permission error with absolute paths, using relative paths: {e}")
        # 相対パスを使用
        workloads_dir = Path(args.workloads_dir)
        output_dir = Path(args.output_dir)
        
        # 出力ディレクトリを作成
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e2:
            print(f"Error creating output directory: {e2}")
            # デフォルトの相対パスを使用
            output_dir = Path("./explain_analyze_results")
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"Using default output directory: {output_dir}")
    except Exception as e:
        print(f"Error with path resolution: {e}")
        # 相対パスを使用
        workloads_dir = Path(args.workloads_dir)
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Trinoクライアントの初期化
    trino_client = TrinoClient(
        host=args.trino_host,
        port=args.trino_port,
        user=args.trino_user,
        catalog=args.trino_catalog,
        schema=args.trino_schema,
        use_sudo=args.sudo
    )
    
    # ワークロード分析器の初期化
    analyzer = WorkloadAnalyzer(str(workloads_dir), str(output_dir), trino_client)
    
    print("=== EXPLAIN ANALYZE Workload Analyzer ===")
    print(f"Workloads directory: {workloads_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Trino connection: {args.trino_host}:{args.trino_port}")
    print(f"Max queries per file: {args.max_queries or 'unlimited'}")
    
    try:
        if args.dataset:
            # 特定のデータセットのみ分析
            analyzer.analyze_dataset(args.dataset, args.max_queries)
        else:
            # すべてのデータセットを分析
            analyzer.analyze_all_datasets(args.max_queries)
        
        print("\n=== Analysis completed ===")
        
    except KeyboardInterrupt:
        print("\n=== Analysis interrupted by user ===")
    except Exception as e:
        print(f"\n=== Analysis failed: {e} ===")
        sys.exit(1)

if __name__ == "__main__":
    main()
