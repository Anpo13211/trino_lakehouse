"""
Upload Parquet files to MinIO
"""

import os
import sys
import argparse
from pathlib import Path
from minio import Minio
from minio.error import S3Error


def upload_parquet_to_minio(dataset_name: str, minio_client: Minio, bucket_name: str = "warehouse"):
    """
    Upload all Parquet files from a dataset directory to MinIO
    """
    parquet_dir = f"zero-shot_datasets/{dataset_name}/parquet_data"
    if not os.path.exists(parquet_dir):
        print(f"Error: Parquet directory {parquet_dir} not found")
        return
    
    print(f"\n=== Uploading {dataset_name} dataset to MinIO ===")
    
    # Ensure bucket exists
    try:
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
            print(f"✓ Created bucket: {bucket_name}")
        else:
            print(f"✓ Bucket exists: {bucket_name}")
    except S3Error as e:
        print(f"Error creating bucket: {e}")
        return
    
    # Upload all parquet files
    parquet_files = [f for f in os.listdir(parquet_dir) if f.endswith('.parquet')]
    
    if not parquet_files:
        print(f"No Parquet files found in {parquet_dir}")
        return
    
    print(f"Found {len(parquet_files)} Parquet files to upload")
    
    uploaded = 0
    for parquet_file in parquet_files:
        local_path = os.path.join(parquet_dir, parquet_file)
        table_name = Path(parquet_file).stem
        object_name = f"zero-shot/{dataset_name}/{table_name}/{parquet_file}"
        
        try:
            minio_client.fput_object(
                bucket_name=bucket_name,
                object_name=object_name,
                file_path=local_path,
                content_type="application/octet-stream"
            )
            print(f"✓ Uploaded: {parquet_file} -> {object_name}")
            uploaded += 1
        except S3Error as e:
            print(f"Error uploading {parquet_file}: {e}")
    
    print(f"\n✓ Successfully uploaded {uploaded} files to MinIO")


def main():
    # MinIO configuration (from docker-compose.yml)
    minio_client = Minio(
        endpoint="localhost:9000",
        access_key="admin",
        secret_key="password",
        secure=False  # HTTP, not HTTPS
    )

    parser = argparse.ArgumentParser(
        description="Upload Parquet files to MinIO"
    )

    parser.add_argument(
        "dataset",
        type=str,
        help="Dataset name (e.g., walmart, tpc_h, ...)"
    )
    
    args = parser.parse_args()
    if args.dataset is None:
        print("Error: Dataset name is required")
        sys.exit(1)
    
    # Upload Walmart dataset
    upload_parquet_to_minio(args.dataset, minio_client)
    
    print("\n=== Upload Complete ===")
    print("You can access MinIO console at: http://localhost:9001")
    print("Login credentials: admin / password")


if __name__ == "__main__":
    main()
