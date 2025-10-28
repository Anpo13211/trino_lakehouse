#!/bin/bash

# Distributed Trino Stop Script

echo "Stopping distributed Trino cluster..."

# Get the base directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Stop Trino coordinator
echo "Stopping Trino coordinator..."
ssh svr10 "cd $SCRIPT_DIR/svr10-coordinator && docker-compose down"

# Stop Trino workers
echo "Stopping Trino workers..."
ssh svr11 "cd $SCRIPT_DIR/svr11-worker && docker-compose down"
ssh svr12 "cd $SCRIPT_DIR/svr12-worker && docker-compose down"

# Stop MinIO
echo "Stopping MinIO..."
ssh svr21 "cd $SCRIPT_DIR/svr21-minio && docker-compose down"

# Stop Polaris + PostgreSQL
echo "Stopping Polaris + PostgreSQL..."
ssh svr20 "cd $SCRIPT_DIR/svr20-polaris && docker-compose down"

echo "All services stopped!"
