"""
Create Trino Iceberg schemas for all datasets in MinIO
"""

import argparse
import os
import sys
import subprocess
from minio import Minio
from minio.error import S3Error


def get_datasets_from_minio(minio_client: Minio, bucket_name: str = "warehouse", prefix: str = "zero-shot/"):
    """
    Get list of dataset names from MinIO by listing directories under the prefix
    """
    datasets = set()
    try:
        objects = minio_client.list_objects(bucket_name, prefix=prefix, recursive=False)
        for obj in objects:
            # obj.object_name will be like "zero-shot/financial/" or "zero-shot/walmart/"
            dataset_path = obj.object_name.replace(prefix, "").strip("/")
            if dataset_path:
                datasets.add(dataset_path)
    except S3Error as e:
        print(f"Error listing objects in MinIO: {e}")
        return []
    
    return sorted(datasets)


def create_schema_in_trino(dataset_name: str, container_name: str = "trino_lakehouse-trino-1", use_sudo: bool = False):
    """
    Create a schema in Trino Iceberg catalog
    """
    schema_name = f"iceberg.{dataset_name}"
    sql_command = f"CREATE SCHEMA IF NOT EXISTS {schema_name};"
    
    # Execute SQL via docker exec
    command = []
    if use_sudo:
        command.append("sudo")
    
    command.extend([
        "docker", "exec", "-i", container_name, "trino",
        "--catalog", "iceberg",
        "--execute", sql_command
    ])
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )
        return True, None
    except subprocess.CalledProcessError as e:
        return False, e.stderr


def main():
    parser = argparse.ArgumentParser(
        description="Create Trino Iceberg schemas for all datasets in MinIO"
    )
    parser.add_argument(
        "--sudo",
        action="store_true",
        help="Use sudo for docker commands (needed on Linux without docker group)"
    )
    args = parser.parse_args()
    
    # Auto-detect if sudo is needed (check if we're on Linux and not in docker group)
    use_sudo = args.sudo
    if not use_sudo and os.name == 'posix':
        # Check if docker command fails without sudo
        try:
            subprocess.run(
                ["docker", "ps"],
                capture_output=True,
                check=True,
                timeout=2
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Note: Docker permission denied. Consider using --sudo flag or adding your user to docker group.")
            print("Attempting with sudo...\n")
            use_sudo = True
    
    print("=== Trino Schema Creator ===\n")
    
    # MinIO configuration
    minio_client = Minio(
        endpoint="localhost:9000",
        access_key="admin",
        secret_key="password",
        secure=False
    )
    
    # Get datasets from MinIO
    print("Fetching datasets from MinIO...")
    datasets = get_datasets_from_minio(minio_client)
    
    if not datasets:
        print("No datasets found in MinIO warehouse/zero-shot/")
        sys.exit(1)
    
    print(f"Found {len(datasets)} datasets: {', '.join(datasets)}\n")
    
    # Create schemas in Trino
    success_count = 0
    failed_count = 0
    
    for dataset in datasets:
        schema_name = f"iceberg.{dataset}"
        print(f"Creating schema: {schema_name}...", end=" ")
        
        success, error = create_schema_in_trino(dataset, use_sudo=use_sudo)
        if success:
            print("✓")
            success_count += 1
        else:
            print(f"✗")
            if error:
                print(f"  Error: {error}")
            failed_count += 1
    
    print(f"\n=== Summary ===")
    print(f"✓ Successfully created: {success_count} schemas")
    if failed_count > 0:
        print(f"✗ Failed: {failed_count} schemas")
    
    sudo_prefix = "sudo " if use_sudo else ""
    print("\nYou can verify schemas with:")
    print(f"  {sudo_prefix}docker exec -it trino_lakehouse-trino-1 trino --execute 'SHOW SCHEMAS IN iceberg;'")


if __name__ == "__main__":
    main()

