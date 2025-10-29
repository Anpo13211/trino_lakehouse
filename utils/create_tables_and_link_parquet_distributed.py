"""
Create Iceberg tables in Trino and link Parquet files from MinIO (Distributed Environment)
"""

import os
import sys
import subprocess
import time
from minio import Minio
from minio.error import S3Error


# SQL reserved keywords that need to be quoted
SQL_RESERVED_KEYWORDS = {
    'order', 'group', 'table', 'select', 'from', 'where', 'join', 'inner', 'outer',
    'left', 'right', 'on', 'as', 'and', 'or', 'not', 'null', 'true', 'false',
    'insert', 'update', 'delete', 'create', 'drop', 'alter', 'index', 'key',
    'primary', 'foreign', 'unique', 'constraint', 'references', 'default',
    'check', 'like', 'in', 'between', 'exists', 'case', 'when', 'then', 'else',
    'end', 'union', 'all', 'distinct', 'having', 'limit', 'offset', 'by',
    'asc', 'desc', 'cast', 'interval', 'timestamp', 'date', 'time',
}


def quote_if_reserved(identifier: str) -> str:
    """
    Quote identifier if it's a SQL reserved keyword or starts with a digit
    """
    # Quote if reserved keyword
    if identifier.lower() in SQL_RESERVED_KEYWORDS:
        return f'"{identifier}"'
    
    # Quote if starts with a digit or contains special characters
    if identifier and (identifier[0].isdigit() or not identifier.replace('_', '').isalnum()):
        return f'"{identifier}"'
    
    return identifier


def get_tables_from_minio(minio_client: Minio, dataset_name: str, bucket_name: str = "warehouse", prefix: str = "zero-shot/"):
    """
    Get list of table names (directories) in MinIO for a dataset
    
    Note: For scaled_* datasets, MinIO uses the name without the scaled_ prefix
    """
    # scaled_* の場合、MinIOのパスからはscaled_プレフィックスを除く
    minio_dataset_name = dataset_name.replace("scaled_", "", 1) if dataset_name.startswith("scaled_") else dataset_name
    
    tables = set()
    full_prefix = f"{prefix}{minio_dataset_name}/"
    
    try:
        objects = minio_client.list_objects(bucket_name, prefix=full_prefix, recursive=False)
        for obj in objects:
            # obj.object_name will be like "zero-shot/imdb/name/"
            table_path = obj.object_name.replace(full_prefix, "").strip("/")
            if table_path:
                tables.add(table_path)
    except S3Error as e:
        print(f"Error listing objects in MinIO: {e}")
        return []
    
    return sorted(tables)


def get_trino_container_name(use_sudo: bool = False):
    """
    Auto-detect Trino container name for distributed environment
    """
    command = []
    if use_sudo:
        command.append("sudo")
    command.extend(["docker", "ps", "--format", "{{.Names}}"])
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=5)
        containers = [name.strip() for name in result.stdout.split('\n') if name.strip()]
        
        # Look for container with '-trino-' pattern (not polaris, not minio-client)
        for container in containers:
            if '-trino-' in container.lower():
                return container
    except:
        pass
    
    # Fallback to distributed environment container name
    return "trino-coordinator"


def execute_sql_in_trino(sql_command: str, container_name: str = None, use_sudo: bool = False, schema: str = None):
    """
    Execute SQL command in Trino
    """
    if container_name is None:
        container_name = get_trino_container_name(use_sudo)
    
    command = []
    if use_sudo:
        command.append("sudo")
    
    command.extend([
        "docker", "exec", container_name, "trino",
        "--catalog", "iceberg"
    ])
    
    # Add schema if specified
    if schema:
        command.extend(["--schema", schema])
    
    command.extend(["--execute", sql_command])
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )
        return True, result.stdout, None
    except subprocess.TimeoutExpired:
        return False, None, "Timeout"
    except subprocess.CalledProcessError as e:
        # Return both stdout and stderr for better error diagnosis
        error_msg = f"STDERR: {e.stderr}\nSTDOUT: {e.stdout}" if e.stdout else e.stderr
        return False, e.stdout, error_msg


def execute_sql_file_in_trino(sql_file_path: str, container_name: str = None, use_sudo: bool = False, schema: str = None):
    """
    Execute SQL file in Trino
    """
    if container_name is None:
        container_name = get_trino_container_name(use_sudo)
    
    if not os.path.exists(sql_file_path):
        return False, None, f"SQL file not found: {sql_file_path}"
    
    with open(sql_file_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # Split into individual statements
    statements = [s.strip() for s in sql_content.split(';') if s.strip()]
    print(f"  Found {len(statements)} SQL statements in file")
    
    for i, stmt in enumerate(statements):
        if not stmt:
            continue
        
        # Skip comments
        if stmt.startswith('--'):
            continue
        
        print(f"  Executing statement {i+1}/{len(statements)}...", end=" ")
        success, output, error = execute_sql_in_trino(stmt + ";", container_name, use_sudo, schema)
        
        if success:
            print("✓")
        else:
            print("✗")
            # Show the actual SQL statement that failed
            print(f"    SQL: {stmt[:150]}...")
            if error:
                # Filter out noise and show meaningful error lines
                error_lines = [line.strip() for line in error.split('\n') 
                              if line.strip() 
                              and 'WARNING' not in line 
                              and 'org.jline' not in line
                              and 'dumb terminal' not in line]
                # Show last 3 lines of error for context
                relevant_errors = error_lines[-3:] if len(error_lines) >= 3 else error_lines
                for err_line in relevant_errors:
                    if err_line:
                        print(f"    Error: {err_line[:400]}")
            if output:
                print(f"    Output: {output[:300]}")
            # Continue with next statement even if one fails
    
    return True, None, None


def link_parquet_files(schema_dataset_name: str, original_dataset_name: str, tables: list, container_name: str = None, use_sudo: bool = False, schema: str = None):
    """
    Link Parquet files from MinIO to Iceberg tables using ALTER TABLE EXECUTE add_files
    
    Args:
        schema_dataset_name: Dataset name for Trino schema/tables (without scaled_ prefix)
        original_dataset_name: Original dataset name (may have scaled_ prefix) for MinIO path
        tables: List of table names
        container_name: Docker container name
        use_sudo: Whether to use sudo for docker commands
    """
    if container_name is None:
        container_name = get_trino_container_name(use_sudo)
    
    print(f"\n=== Linking Parquet files for {original_dataset_name} ===")
    
    success_count = 0
    failed_count = 0
    
    for table_name in tables:
        # Quote table name if it's a reserved keyword
        quoted_table_name = quote_if_reserved(table_name)
        
        # Use schema_dataset_name for Trino table names
        full_table_name = f"iceberg.{schema_dataset_name}.{quoted_table_name}"
        # Use schema_dataset_name for MinIO path (already has scaled_ removed if applicable)
        s3_location = f"s3a://warehouse/zero-shot/{schema_dataset_name}/{table_name}/"
        
        alter_sql = f"""ALTER TABLE {full_table_name}
EXECUTE add_files(
  location => '{s3_location}',
  format   => 'PARQUET'
);"""
        
        print(f"  Linking {table_name}...", end=" ")
        success, output, error = execute_sql_in_trino(alter_sql, container_name, use_sudo, schema)
        
        if success:
            print("✓")
            success_count += 1
        else:
            # Check if error is "File already exists" (not a real error)
            if error and 'File already exists' in error:
                print("⊗ (already linked)")
                success_count += 1  # Count as success
            else:
                print("✗")
                if error:
                    # Show detailed error for debugging
                    error_lines = [line.strip() for line in error.split('\n') 
                                  if line.strip() 
                                  and 'WARNING' not in line
                                  and 'org.jline' not in line
                                  and 'dumb terminal' not in line]
                    # Show last 3 lines for context
                    relevant_errors = error_lines[-3:] if len(error_lines) >= 3 else error_lines
                    for err_line in relevant_errors:
                        if err_line:
                            print(f"    Error: {err_line[:400]}")
                if output:
                    print(f"    Output: {output[:300]}")
                failed_count += 1
        
        # Small delay to avoid overwhelming Trino
        time.sleep(0.5)
    
    return success_count, failed_count


def process_dataset(dataset_name: str, minio_client: Minio, use_sudo: bool = False):
    """
    Create tables and link Parquet files for a dataset
    """
    print(f"\n{'='*60}")
    print(f"Processing dataset: {dataset_name}")
    
    # For scaled_* datasets, use the name without scaled_ prefix for schema/table names
    schema_dataset_name = dataset_name.replace("scaled_", "", 1) if dataset_name.startswith("scaled_") else dataset_name
    
    # Show MinIO path and Trino schema if scaled_* dataset
    if dataset_name.startswith("scaled_"):
        print(f"  (MinIO path: zero-shot/{schema_dataset_name}/)")
        print(f"  (Trino schema: iceberg.{schema_dataset_name})")
    
    print('='*60)
    
    # Check if DDL file exists
    # For scaled_* datasets, DDL file is in the directory without scaled_ prefix
    ddl_file = f"zero-shot_datasets/{schema_dataset_name}/schema_sql/iceberg.sql"
    if not os.path.exists(ddl_file):
        print(f"✗ DDL file not found: {ddl_file}")
        print(f"  Run: python utils/generate_iceberg_ddl_from_parquet.py {dataset_name} --with-schema")
        return False
    
    # Get tables from MinIO
    tables = get_tables_from_minio(minio_client, dataset_name)
    if not tables:
        print(f"✗ No tables found in MinIO for {dataset_name}")
        return False
    
    print(f"Found {len(tables)} tables in MinIO: {', '.join(tables)}")
    
    # Create schema if it doesn't exist (use schema_dataset_name, not dataset_name)
    schema_name = f"iceberg.{schema_dataset_name}"
    create_schema_sql = f"CREATE SCHEMA IF NOT EXISTS {schema_name};"
    print(f"\n=== Creating schema {schema_name} ===")
    success, output, error = execute_sql_in_trino(create_schema_sql, use_sudo=use_sudo, schema="default")
    if success:
        print("✓ Schema ready")
    else:
        print(f"✗ Failed to create schema")
        if error:
            print(f"  Error (stderr): {error[:500]}")
        if output:
            print(f"  Output (stdout): {output[:500]}")
        # Don't fail completely - schema might already exist
        # return False
    
    # Execute DDL file to create tables
    print(f"\n=== Creating tables from {ddl_file} ===")
    success, output, error = execute_sql_file_in_trino(ddl_file, use_sudo=use_sudo, schema=schema_dataset_name)
    
    if not success:
        print(f"✗ Failed to execute DDL file")
        return False
    
    print("✓ Tables created successfully")
    
    # Link Parquet files (pass schema_dataset_name for Trino table names)
    success_count, failed_count = link_parquet_files(schema_dataset_name, dataset_name, tables, use_sudo=use_sudo, schema=schema_dataset_name)
    
    print(f"\n{'='*60}")
    print(f"Summary for {dataset_name}:")
    print(f"  ✓ Successfully linked: {success_count} tables")
    if failed_count > 0:
        print(f"  ✗ Failed: {failed_count} tables")
    print('='*60)
    
    return True


def find_all_datasets_with_ddl_and_parquet():
    """
    Find all datasets that have both iceberg.sql and parquet files
    
    Note: If both scaled_* and the original dataset exist, only process scaled_*
    """
    datasets = []
    scaled_datasets = set()
    zero_shot_dir = "zero-shot_datasets"
    if not os.path.exists(zero_shot_dir):
        return datasets
    
    for item in os.listdir(zero_shot_dir):
        item_path = os.path.join(zero_shot_dir, item)
        if os.path.isdir(item_path):
            parquet_dir = os.path.join(item_path, "parquet_data")
            
            # Only consider datasets that have parquet_data directory
            if os.path.exists(parquet_dir):
                datasets.append(item)
                
                # Track scaled datasets
                if item.startswith("scaled_"):
                    original_name = item.replace("scaled_", "", 1)
                    scaled_datasets.add(original_name)
    
    # Filter out original datasets if scaled version exists
    filtered_datasets = [d for d in datasets if not (d in scaled_datasets)]
    
    return sorted(filtered_datasets)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Create Iceberg tables in Trino and link Parquet files from MinIO (Distributed Environment)"
    )
    parser.add_argument(
        "dataset",
        type=str,
        nargs='?',
        help="Dataset name. If not specified, processes all datasets with iceberg.sql."
    )
    parser.add_argument(
        "--sudo",
        action="store_true",
        help="Use sudo for docker commands (needed on Linux without docker group)"
    )
    
    args = parser.parse_args()
    
    # Auto-detect if sudo is needed
    use_sudo = args.sudo
    if not use_sudo and os.name == 'posix':
        try:
            subprocess.run(
                ["docker", "ps"],
                capture_output=True,
                check=True,
                timeout=2
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Note: Docker permission denied. Using sudo...")
            use_sudo = True
    
    print("="*60)
    print("Iceberg Table Creator & Parquet Linker (Distributed Environment)")
    print("="*60)
    
    # MinIO configuration for distributed environment
    minio_client = Minio(
        endpoint="192.168.8.150:9000",  # svr21 MinIO endpoint
        access_key="admin",
        secret_key="password",
        secure=False
    )
    
    if args.dataset:
        # Process specific dataset
        success = process_dataset(args.dataset, minio_client, use_sudo)
        if not success:
            sys.exit(1)
    else:
        # Process all datasets
        datasets = find_all_datasets_with_ddl_and_parquet()
        if not datasets:
            print("\nNo datasets with iceberg.sql found")
            print("Run: python utils/generate_iceberg_ddl_from_parquet.py --with-schema")
            sys.exit(1)
        
        print(f"\nFound {len(datasets)} datasets with iceberg.sql\n")
        
        success_count = 0
        for dataset in datasets:
            if process_dataset(dataset, minio_client, use_sudo):
                success_count += 1
        
        print(f"\n{'='*60}")
        print(f"Final Summary:")
        print(f"  ✓ Successfully processed: {success_count}/{len(datasets)} datasets")
        print('='*60)
    
    print("\nYou can verify tables with:")
    sudo_prefix = "sudo " if use_sudo else ""
    container_name = get_trino_container_name(use_sudo)
    print(f"  {sudo_prefix}docker exec {container_name} trino --execute 'SHOW TABLES IN iceberg.<dataset_name>;'")
    print(f"  {sudo_prefix}docker exec {container_name} trino --execute 'SELECT * FROM iceberg.<dataset_name>.<table_name> LIMIT 5;'")


if __name__ == "__main__":
    main()
