#!/bin/bash

# Distributed Trino Deployment Script

echo "Starting distributed Trino deployment..."

# Deploy Polaris + PostgreSQL on svr20
echo "Deploying Polaris + PostgreSQL on svr20..."
ssh svr20 "cd /path/to/svr20-polaris && docker-compose up -d"

# Deploy MinIO on svr21
echo "Deploying MinIO on svr21..."
ssh svr21 "cd /path/to/svr21-minio && docker-compose up -d"

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 30

# Deploy Trino workers
echo "Deploying Trino workers..."
ssh svr11 "cd /path/to/svr11-worker && docker-compose up -d"
ssh svr12 "cd /path/to/svr12-worker && docker-compose up -d"

# Wait for workers to be ready
echo "Waiting for workers to be ready..."
sleep 30

# Deploy Trino coordinator
echo "Deploying Trino coordinator..."
ssh svr10 "cd /path/to/svr10-coordinator && docker-compose up -d"

echo "Deployment completed!"
echo "Trino Web UI: http://192.168.8.80:8080"
echo "MinIO Console: http://192.168.8.150:9001"
echo "Polaris Catalog: http://192.168.8.140:8080"
