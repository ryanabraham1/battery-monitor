#!/bin/sh
# Installs the IR hub on Raspberry Pi OS (Bookworm or later) with an MCP2515 CAN HAT.
#   sudo ./install.sh <crystal Hz>      e.g. 12000000 or 8000000 (read it off the HAT's crystal)
set -e
OSC="${1:-12000000}"
DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_AS="${SUDO_USER:-$(id -un)}"
CFG=/boot/firmware/config.txt
[ -f "$CFG" ] || CFG=/boot/config.txt

if [ "$(id -u)" != 0 ]; then echo "run with sudo"; exit 1; fi

apt-get update
apt-get install -y python3-can can-utils

if ! grep -q "mcp2515-can0" "$CFG"; then
  printf '\n# CAN HAT for the battery IR hub\ndtparam=spi=on\ndtoverlay=mcp2515-can0,oscillator=%s,interrupt=25,spimaxfrequency=2000000\n' "$OSC" >> "$CFG"
  echo "added the MCP2515 overlay to $CFG"
else
  echo "$CFG already has an mcp2515 overlay; left unchanged"
fi

cat > /etc/systemd/system/irhub.service <<EOF
[Unit]
Description=FRC battery IR hub
After=network.target

[Service]
User=$RUN_AS
WorkingDirectory=$DIR
ExecStartPre=+/bin/sh -c 'ip link set can0 down 2>/dev/null; ip link set can0 up type can bitrate 250000 restart-ms 100'
ExecStart=/usr/bin/python3 $DIR/irhub.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable irhub.service
echo "done. Reboot, then open http://$(hostname).local:8080"
echo "logs: journalctl -u irhub -f     raw bus traffic: candump can0"
