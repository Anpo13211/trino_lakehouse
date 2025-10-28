#!/bin/bash

# Distributed Trino Configuration Verification Script

echo "============================================"
echo "分散Trinoセットアップ - 設定検証スクリプト"
echo "============================================"
echo ""

ERRORS=0
WARNINGS=0

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check file exists
check_file() {
    local file=$1
    local description=$2
    
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $description: $file"
    else
        echo -e "${RED}✗${NC} $description: $file (NOT FOUND)"
        ((ERRORS++))
    fi
}

# Function to check content in file
check_content() {
    local file=$1
    local pattern=$2
    local description=$3
    
    if [ ! -f "$file" ]; then
        return
    fi
    
    if grep -q "$pattern" "$file"; then
        echo -e "${GREEN}✓${NC} $description"
    else
        echo -e "${RED}✗${NC} $description (PATTERN NOT FOUND: $pattern)"
        ((ERRORS++))
    fi
}

# Function to warn about content
warn_content() {
    local file=$1
    local pattern=$2
    local description=$3
    
    if [ ! -f "$file" ]; then
        return
    fi
    
    if grep -q "$pattern" "$file"; then
        echo -e "${YELLOW}⚠${NC} $description"
        ((WARNINGS++))
    fi
}

echo "=== Docker Compose Files ==="
check_file "svr10-coordinator/docker-compose.yml" "Coordinator compose"
check_file "svr11-worker/docker-compose.yml" "Worker 11 compose"
check_file "svr12-worker/docker-compose.yml" "Worker 12 compose"
check_file "svr20-polaris/docker-compose.yml" "Polaris compose"
check_file "svr21-minio/docker-compose.yml" "MinIO compose"
echo ""

echo "=== Coordinator Configuration ==="
check_file "svr10-coordinator/config/config.properties" "Config properties"
check_file "svr10-coordinator/config/node.properties" "Node properties"
check_file "svr10-coordinator/config/jvm.config" "JVM config"
check_content "svr10-coordinator/config/config.properties" "coordinator=true" "Coordinator role enabled"
check_content "svr10-coordinator/config/config.properties" "discovery-server.enabled=true" "Discovery server enabled"
check_content "svr10-coordinator/config/config.properties" "distributed-joins-enabled=true" "Distributed joins enabled"
check_content "svr10-coordinator/config/node.properties" "192.168.8.80" "Coordinator IP set"
echo ""

echo "=== Worker 11 Configuration ==="
check_file "svr11-worker/config/config.properties" "Config properties"
check_file "svr11-worker/config/node.properties" "Node properties"
check_content "svr11-worker/config/config.properties" "coordinator=false" "Worker role set"
check_content "svr11-worker/config/config.properties" "discovery.uri=http://192.168.8.80:8080" "Discovery URI set"
check_content "svr11-worker/config/node.properties" "192.168.8.90" "Worker 11 IP set"
check_content "svr11-worker/config/node.properties" "node.id=worker-11" "Node ID set"
echo ""

echo "=== Worker 12 Configuration ==="
check_file "svr12-worker/config/config.properties" "Config properties"
check_file "svr12-worker/config/node.properties" "Node properties"
check_content "svr12-worker/config/config.properties" "coordinator=false" "Worker role set"
check_content "svr12-worker/config/config.properties" "discovery.uri=http://192.168.8.80:8080" "Discovery URI set"
check_content "svr12-worker/config/node.properties" "192.168.8.100" "Worker 12 IP set"
check_content "svr12-worker/config/node.properties" "node.id=worker-12" "Node ID set"
echo ""

echo "=== Catalog Configuration ==="
check_file "svr10-coordinator/config/catalog/iceberg.properties" "Coordinator Iceberg catalog"
check_file "svr10-coordinator/config/catalog/tpch.properties" "Coordinator TPC-H catalog"
check_file "svr10-coordinator/config/catalog/memory.properties" "Coordinator Memory catalog"

check_file "svr11-worker/config/catalog/iceberg.properties" "Worker 11 Iceberg catalog"
check_file "svr12-worker/config/catalog/iceberg.properties" "Worker 12 Iceberg catalog"
echo ""

echo "=== Iceberg Configuration Validation ==="
check_content "svr10-coordinator/config/catalog/iceberg.properties" "iceberg.rest-catalog.security=OAUTH2" "OAuth2 security enabled"
check_content "svr10-coordinator/config/catalog/iceberg.properties" "iceberg.rest-catalog.oauth2.credential=root:secret" "OAuth2 credentials set"
check_content "svr10-coordinator/config/catalog/iceberg.properties" "192.168.8.140:8181" "Polaris endpoint set"
check_content "svr10-coordinator/config/catalog/iceberg.properties" "192.168.8.150:9000" "MinIO endpoint set"
check_content "svr10-coordinator/config/catalog/iceberg.properties" "s3.aws-access-key=admin" "S3 access key set"

check_content "svr11-worker/config/catalog/iceberg.properties" "iceberg.rest-catalog.security=OAUTH2" "Worker 11 OAuth2 enabled"
check_content "svr12-worker/config/catalog/iceberg.properties" "iceberg.rest-catalog.security=OAUTH2" "Worker 12 OAuth2 enabled"
echo ""

echo "=== Polaris Configuration ==="
check_content "svr20-polaris/docker-compose.yml" "polaris-admin-bootstrap" "Bootstrap container configured"
check_content "svr20-polaris/docker-compose.yml" "default-realm,root,secret" "Bootstrap credentials set"
check_content "svr20-polaris/docker-compose.yml" "POLARIS_PERSISTENCE_TYPE: relational-jdbc" "JDBC persistence configured"
check_content "svr20-polaris/docker-compose.yml" "healthcheck" "PostgreSQL healthcheck configured"
echo ""

echo "=== MinIO Configuration ==="
check_content "svr21-minio/docker-compose.yml" "minio-client" "MinIO client configured"
check_content "svr21-minio/docker-compose.yml" "mc mb minio/warehouse" "Warehouse bucket auto-creation"
check_content "svr21-minio/docker-compose.yml" "MINIO_ROOT_USER: admin" "MinIO credentials set"
echo ""

echo "=== Scripts ==="
check_file "deploy.sh" "Deploy script"
check_file "health-check.sh" "Health check script"
check_file "stop.sh" "Stop script"

# Check if scripts are executable
if [ -x "deploy.sh" ]; then
    echo -e "${GREEN}✓${NC} deploy.sh is executable"
else
    echo -e "${YELLOW}⚠${NC} deploy.sh is not executable (run: chmod +x deploy.sh)"
    ((WARNINGS++))
fi

if [ -x "health-check.sh" ]; then
    echo -e "${GREEN}✓${NC} health-check.sh is executable"
else
    echo -e "${YELLOW}⚠${NC} health-check.sh is not executable (run: chmod +x health-check.sh)"
    ((WARNINGS++))
fi
echo ""

echo "=== Consistency Checks ==="
# Check that all Iceberg configs use same credentials
COORDINATOR_CREDS=$(grep "s3.aws-access-key" svr10-coordinator/config/catalog/iceberg.properties 2>/dev/null | cut -d'=' -f2)
WORKER11_CREDS=$(grep "s3.aws-access-key" svr11-worker/config/catalog/iceberg.properties 2>/dev/null | cut -d'=' -f2)
WORKER12_CREDS=$(grep "s3.aws-access-key" svr12-worker/config/catalog/iceberg.properties 2>/dev/null | cut -d'=' -f2)

if [ "$COORDINATOR_CREDS" = "$WORKER11_CREDS" ] && [ "$COORDINATOR_CREDS" = "$WORKER12_CREDS" ]; then
    echo -e "${GREEN}✓${NC} S3 credentials consistent across all nodes"
else
    echo -e "${RED}✗${NC} S3 credentials mismatch between nodes"
    ((ERRORS++))
fi

# Check OAuth2 credentials consistency
COORD_OAUTH=$(grep "oauth2.credential" svr10-coordinator/config/catalog/iceberg.properties 2>/dev/null | cut -d'=' -f2)
W11_OAUTH=$(grep "oauth2.credential" svr11-worker/config/catalog/iceberg.properties 2>/dev/null | cut -d'=' -f2)
W12_OAUTH=$(grep "oauth2.credential" svr12-worker/config/catalog/iceberg.properties 2>/dev/null | cut -d'=' -f2)

if [ "$COORD_OAUTH" = "$W11_OAUTH" ] && [ "$COORD_OAUTH" = "$W12_OAUTH" ]; then
    echo -e "${GREEN}✓${NC} OAuth2 credentials consistent across all nodes"
else
    echo -e "${RED}✗${NC} OAuth2 credentials mismatch between nodes"
    ((ERRORS++))
fi
echo ""

echo "============================================"
echo "検証結果"
echo "============================================"
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ すべての設定が正しく構成されています！${NC}"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ 警告が ${WARNINGS} 件あります（デプロイは可能）${NC}"
    exit 0
else
    echo -e "${RED}✗ エラーが ${ERRORS} 件見つかりました${NC}"
    echo -e "${YELLOW}⚠ 警告が ${WARNINGS} 件あります${NC}"
    echo ""
    echo "デプロイ前にエラーを修正してください。"
    exit 1
fi


