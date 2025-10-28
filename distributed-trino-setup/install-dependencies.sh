#!/bin/bash
set -e

echo "=== Installing Docker & Python 3.10 venv ==="

# 更新
sudo apt-get update -y

# 必要パッケージ
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# Docker GPGキーとリポジトリ登録
sudo install -m 0755 -d /etc/apt/keyrings
sudo rm -f /etc/apt/keyrings/docker.gpg
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker インストール
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Docker 起動 & 自動起動設定
sudo systemctl enable --now docker

# 権限追加
sudo usermod -aG docker $USER

# Python3.10 + venv (Ubuntu 22.04 はデフォルトで3.10が入っている)
sudo apt-get install -y python3.10 python3.10-venv python3-pip

# 確認
echo ""
echo "=== Versions ==="
docker --version
docker compose version
python3.10 --version
