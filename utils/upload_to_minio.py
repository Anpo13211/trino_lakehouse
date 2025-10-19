"""
Upload Parquet files to MinIO
"""

import os
import sys
import argparse
from pathlib import Path
from minio import Minio
from minio.error import S3Error


def upload_parquet_to_minio(dataset_name: str, minio_client: Minio, bucket_name: str = "warehouse", show_bucket_message: bool = True):
    """
    Upload all Parquet files from a dataset directory to MinIO
    """
    parquet_dir = f"zero-shot_datasets/{dataset_name}/parquet_data"
    if not os.path.exists(parquet_dir):
        print(f"Skipping {dataset_name}: Parquet directory not found")
        return 0
    
    # scaled_* の場合、MinIOのパスからはscaled_プレフィックスを除く
    minio_dataset_name = dataset_name.replace("scaled_", "", 1) if dataset_name.startswith("scaled_") else dataset_name
    
    print(f"=== Uploading {dataset_name} dataset to MinIO (as {minio_dataset_name}) ===")
    
    # Ensure bucket exists
    if show_bucket_message:
        try:
            if not minio_client.bucket_exists(bucket_name):
                minio_client.make_bucket(bucket_name)
                print(f"✓ Created bucket: {bucket_name}")
            else:
                print(f"✓ Bucket exists: {bucket_name}")
        except S3Error as e:
            print(f"Error creating bucket: {e}")
            return 0
    
    # Upload all parquet files
    parquet_files = [f for f in os.listdir(parquet_dir) if f.endswith('.parquet')]
    
    if not parquet_files:
        print(f"No Parquet files found in {parquet_dir}")
        return 0
    
    print(f"Found {len(parquet_files)} Parquet files")
    
    uploaded = 0
    for parquet_file in parquet_files:
        local_path = os.path.join(parquet_dir, parquet_file)
        table_name = Path(parquet_file).stem
        object_name = f"zero-shot/{minio_dataset_name}/{table_name}/{parquet_file}"
        
        try:
            minio_client.fput_object(
                bucket_name=bucket_name,
                object_name=object_name,
                file_path=local_path,
                content_type="application/octet-stream"
            )
            # print(f"✓ Uploaded: {parquet_file} -> {object_name}")
            uploaded += 1
        except S3Error as e:
            print(f"Error uploading {parquet_file}: {e}")
    
    print(f"✓ Successfully uploaded {uploaded} files")
    return uploaded


def find_all_datasets_with_parquet():
    """
    Find all datasets that have parquet_data directory
    """
    datasets = []
    zero_shot_dir = "zero-shot_datasets"
    if not os.path.exists(zero_shot_dir):
        return datasets
    
    for item in os.listdir(zero_shot_dir):
        item_path = os.path.join(zero_shot_dir, item)
        if os.path.isdir(item_path):
            parquet_dir = os.path.join(item_path, "parquet_data")
            if os.path.exists(parquet_dir):
                datasets.append(item)
    
    return sorted(datasets)


def main():
    # MinIO configuration (from docker-compose.yml)
    minio_client = Minio(
        endpoint="localhost:9000",
        access_key="admin",
        secret_key="password",
        secure=False  # HTTP, not HTTPS
    )

    parser = argparse.ArgumentParser(
        description="Upload Parquet files to MinIO. If no dataset is specified, uploads all datasets with parquet_data."
    )

    parser.add_argument(
        "dataset",
        type=str,
        nargs='?',  # Make argument optional
        help="Dataset name (e.g., walmart, tpc_h, ...). If not specified, uploads all datasets."
    )
    
    args = parser.parse_args()
    
    # Ensure bucket exists (check once at the beginning)
    bucket_name = "warehouse"
    try:
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
            print(f"✓ Created bucket: {bucket_name}")
        else:
            print(f"✓ Bucket exists: {bucket_name}")
    except S3Error as e:
        print(f"Error with bucket: {e}")
        sys.exit(1)
    
    print()
    
    if args.dataset:
        # Upload specific dataset
        total = upload_parquet_to_minio(args.dataset, minio_client, show_bucket_message=False)
        print(f"\n=== Upload Complete: {total} files uploaded ===")
    else:
        # Upload all datasets
        datasets = find_all_datasets_with_parquet()
        if not datasets:
            print("No datasets with parquet_data found")
            sys.exit(1)
        
        print(f"Found {len(datasets)} datasets with parquet_data")
        print(f"Datasets: {', '.join(datasets)}\n")
        
        total_uploaded = 0
        for dataset in datasets:
            uploaded = upload_parquet_to_minio(dataset, minio_client, show_bucket_message=False)
            total_uploaded += uploaded
            print()
        
        print(f"=== All Uploads Complete: {total_uploaded} files uploaded from {len(datasets)} datasets ===")
    
    print("You can access MinIO console at: http://localhost:9001")
    print("Login credentials: admin / password")


if __name__ == "__main__":
    main()
