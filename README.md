# Pool Controller

A self-hosted web app for controlling a **Hayward AquaLogic / ProLogic** pool controller from your phone.

![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red)

## What It Does

- Real-time control of your pool equipment (filter, lights, heater, spa, aux relays) from any browser
- Live temperature, salt level, chlorinator, and pump data via Server-Sent Events
- Single-file HTML app — no build tools, no npm, no framework
- Python bridge talks to the AquaLogic board over RS-485
- Runs on a Raspberry Pi Zero 2W (~$15) with a MAX485 module (~$3)

## Architecture

```
┌──────────────┐    RS-485     ┌───────────┐    HTTP/SSE    ┌──────────┐
│  AquaLogic   │◄────────────►│  Pi Zero   │◄─────────────►│  Phone / │
│  Controller  │  REMOTE      │  + MAX485  │  Port 4200    │  Browser │
│  (007-243-01)│  DISPLAY     │            │               │          │
└──────────────┘  port        └───────────┘               └──────────┘
                                   │
                              pool_bridge.py
                              (aqualogic lib)
```

## Hardware Required

| Item | Cost |
|------|------|
| Raspberry Pi Zero 2W | ~$15 |
| MicroSD card (16GB+) | ~$8 |
| MAX485 TTL-to-RS-485 module | ~$3 |
| USB-C 5V 2.5A power supply | ~$10 |
| Female-to-Female jumper wires | ~$5 |
| **Total** | **~$41** |

## Quick Start

### 1. Wire MAX485 to AquaLogic

Connect to the **REMOTE DISPLAY** port (empty 4-pin header on board 007-243-01):

```
MAX485 Pin    →   Connection
──────────────────────────────────────
A  (DATA+)    →   REMOTE DISPLAY Pin 3 (YEL)
B  (DATA−)    →   REMOTE DISPLAY Pin 2 (BLK)
GND           →   REMOTE DISPLAY Pin 4 (GRN)
VCC           →   Pi 3.3V   (Pin 1)
GND           →   Pi GND    (Pin 6)
DI  (TX)      →   Pi GPIO14 (Pin 8)
DE            →   Pi GPIO18 (Pin 12)
RE            →   Pi GND    (Pin 6)
RO  (RX)      →   Pi GPIO15 (Pin 10)
```

> ⚠️ **Do NOT connect Pin 1 (RED / +12V)** from the REMOTE DISPLAY port to anything.

### 2. Set up the Pi

Flash Raspberry Pi OS Lite (64-bit), enable SSH and WiFi in the imager, then:

```bash
# Enable serial port
sudo raspi-config  # Interface Options → Serial Port → No login shell, Yes hardware

# Add to /boot/firmware/config.txt:
echo -e "enable_uart=1\ndtoverlay=disable-bt" | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

### 3. Install and run the bridge

```bash
sudo apt update && sudo apt install -y python3-pip python3-serial
pip3 install aqualogic --break-system-packages

# Copy pool_bridge.py to the Pi, then:
python3 pool_bridge.py
```

Test it:
```bash
curl http://localhost:4200/state/all
```

### 4. Serve the web app

```bash
sudo apt install -y nginx
sudo mkdir -p /var/www/pool
sudo cp index.html /var/www/pool/index.html
```

Configure nginx — see the built-in setup guide in the app for the full config.

### 5. Open on your phone

Navigate to `http://poolcontroller.local` on the same WiFi. Tap the status badge to connect.

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/state/all` | GET | Full state JSON (temps, circuits, salt, pump) |
| `/state/circuit/setState` | PUT | Toggle a circuit |
| `/events` | SSE | Live state push via Server-Sent Events |
| `/health` | GET | Health check |

### Toggle a circuit

```bash
curl -X PUT http://PI_IP:4200/state/circuit/setState \
  -H "Content-Type: application/json" \
  -d '{"circuit": "FILTER", "state": true}'
```

### Valid circuit names

```
FILTER  POOL  SPA  SPILLOVER  LIGHTS  HEATER_1
AUX_1  AUX_2  AUX_3  AUX_4  AUX_5  AUX_6
VALVE_3  VALVE_4  HEATER_AUTO_MODE  FILTER_LOW_SPEED
SUPER_CHLORINATE
```

## Auto-Start on Boot

```bash
sudo cp scripts/poolbridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable poolbridge
sudo systemctl start poolbridge
```

## Remote Access

Install [Tailscale](https://tailscale.com/download) on the Pi and your phone for free, secure access from anywhere — no port forwarding needed.

## Built With

- [aqualogic](https://github.com/swilson/aqualogic) — Python library for the Hayward/Goldline AquaLogic RS-485 protocol
- Vanilla HTML/CSS/JS — no dependencies, no build step

## Compatibility

Tested with:
- Hayward AquaLogic (board 007-243-01)
- Should also work with ProLogic controllers using the same RS-485 protocol

## License

MIT
