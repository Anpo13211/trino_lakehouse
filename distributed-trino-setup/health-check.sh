#!/bin/bash

# Health Check Script for Distributed Trino Setup

echo "Checking distributed Trino cluster health..."

# Function to check if service is responding
check_service() {
    local service_name=$1
    local url=$2
    local max_attempts=30
    local attempt=1
    
    echo "Checking $service_name at $url..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo "✅ $service_name is healthy"
            return 0
        fi
        echo "⏳ Attempt $attempt/$max_attempts - waiting for $service_name..."
        sleep 10
        attempt=$((attempt + 1))
    done
    
    echo "❌ $service_name is not responding after $max_attempts attempts"
    return 1
}

# Check all services
echo "=== Health Check Results ==="

# Check Trino Coordinator
check_service "Trino Coordinator" "http://192.168.8.80:8080/v1/info"

# Check MinIO
check_service "MinIO" "http://192.168.8.150:9000/minio/health/live"

# Check Polaris Catalog
check_service "Polaris Catalog" "http://192.168.8.140:8181/api/catalog/v1/config"

echo ""
echo "=== Cluster Status ==="
echo "Trino Web UI: http://192.168.8.80:8080"
echo "MinIO Console: http://192.168.8.150:9001"
echo "Polaris Catalog: http://192.168.8.140:8181"

# Check if workers are registered
echo ""
echo "=== Worker Status ==="
curl -s "http://192.168.8.80:8080/v1/status" | grep -o '"activeNodes":[0-9]*' || echo "Could not retrieve worker status"
