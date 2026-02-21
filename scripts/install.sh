#!/bin/bash
# ──────────────────────────────────────────────────────
# Pool Controller — One-command installer
# Run on your Raspberry Pi via SSH:
#   curl -fsSL https://raw.githubusercontent.com/YOUR_USER/pool-controller/main/scripts/install.sh | bash
#   — or —
#   bash install.sh
# ──────────────────────────────────────────────────────
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🏊 Pool Controller Installer${NC}"
echo "──────────────────────────────────────"

# 1. Dependencies
echo -e "\n${YELLOW}[1/5] Installing dependencies...${NC}"
sudo apt update -qq
sudo apt install -y -qq python3-pip python3-serial nginx > /dev/null 2>&1
pip3 install aqualogic --break-system-packages -q

# 2. Bridge
echo -e "${YELLOW}[2/5] Installing bridge...${NC}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$REPO_DIR/pool_bridge.py" ]; then
    cp "$REPO_DIR/pool_bridge.py" /home/pi/pool_bridge.py
else
    echo -e "${RED}Error: pool_bridge.py not found. Run from the repo directory.${NC}"
    exit 1
fi

# 3. Web app
echo -e "${YELLOW}[3/5] Deploying web app...${NC}"
sudo mkdir -p /var/www/pool
if [ -f "$REPO_DIR/index.html" ]; then
    sudo cp "$REPO_DIR/index.html" /var/www/pool/index.html
else
    echo -e "${RED}Error: index.html not found.${NC}"
    exit 1
fi

# 4. Nginx
echo -e "${YELLOW}[4/5] Configuring nginx...${NC}"
sudo cp "$REPO_DIR/scripts/nginx-pool.conf" /etc/nginx/sites-available/default
sudo systemctl restart nginx

# 5. Systemd service
echo -e "${YELLOW}[5/5] Setting up auto-start...${NC}"
sudo cp "$REPO_DIR/scripts/poolbridge.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable poolbridge
sudo systemctl start poolbridge

echo ""
echo -e "${GREEN}✅ Installation complete!${NC}"
echo "──────────────────────────────────────"
echo "Bridge:  http://localhost:4200/state/all"
echo "Web app: http://$(hostname).local"
echo ""
echo "Check status:  sudo systemctl status poolbridge"
echo "View logs:     journalctl -u poolbridge -f"
echo ""
echo -e "${YELLOW}⚠️  Make sure serial is enabled (raspi-config → Interface → Serial)${NC}"
echo -e "${YELLOW}⚠️  Make sure /boot/firmware/config.txt has: enable_uart=1 and dtoverlay=disable-bt${NC}"
