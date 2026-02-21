# Jared's Pool Controller

Control your Hayward AquaLogic pool from your phone. Filter, lights, heater, spa — all from a browser, no app install needed.

A Raspberry Pi sits in your pool equipment closet, wired to the AquaLogic board over RS-485. It runs a tiny Python program that reads temperatures, salt levels, and equipment status in real time — and lets you toggle everything on and off from any device on your WiFi.

```
┌──────────────┐    RS-485     ┌────────────┐    HTTP/SSE    ┌──────────┐
│  AquaLogic   │◄─────────────►│  Pi Zero   │◄──────────────►│  Phone / │
│  Controller  │  REMOTE       │  + MAX485  │  Port 4200     │  Browser │
│  (007-243-01)│  DISPLAY      │            │                │          │
└──────────────┘  port         └────────────┘                └──────────┘
                                     │
                                pool_bridge.py
                                (aqualogic lib)
```

**Total cost: ~$41.** About 30 minutes of hands-on time once you have the parts.

---

## What You Need to Buy

| Item | Approx. Cost | Where to Get It |
|------|-------------|-----------------|
| Raspberry Pi Zero 2W | ~$15 | [rpilocator.com](https://rpilocator.com) or Amazon |
| MicroSD card (16 GB or bigger) | ~$8 | Amazon, Best Buy, anywhere |
| MAX485 TTL-to-RS-485 module | ~$3 | Amazon — search "MAX485 module" (the tiny blue board) |
| USB-C power supply (5V, 2.5A) | ~$10 | Any phone charger that's USB-C and at least 2.5A works |
| Female-to-female jumper wires (6+) | ~$5 | Amazon — Dupont jumper wires |

You'll also need a computer with an SD card slot (or a USB adapter) to set up the Pi's SD card.

---

## Step 1: Flash the SD Card

This puts the operating system onto the MicroSD card so the Pi can boot.

1. On your computer, download and install **Raspberry Pi Imager** from [raspberrypi.com/software](https://www.raspberrypi.com/software/).
2. Insert your MicroSD card into your computer.
3. Open Raspberry Pi Imager and choose:
   - **Device:** Raspberry Pi Zero 2W
   - **Operating System:** Raspberry Pi OS Lite (64-bit) — it's under "Raspberry Pi OS (other)"
   - **Storage:** Your MicroSD card
4. **Before you click Write**, click the gear icon (or "Edit Settings") and fill in:
   - **Hostname:** `poolcontroller` (this is how you'll find it on your network)
   - **Enable SSH:** Yes, use password authentication
   - **Username:** `pi`
   - **Password:** pick something you'll remember
   - **WiFi:** enter your home WiFi name and password
   - **Country:** your country code (US, etc.)
5. Click **Write** and wait for it to finish. It takes a few minutes.
6. Put the SD card into the Pi. Don't power it on yet — do the wiring first.

**If it fails to write:** Try a different SD card. Cheap cards sometimes have bad sectors. Also make sure nothing else is using the card (close File Explorer / Finder windows showing the card).

---

## Step 2: Wire the MAX485 Module

This is the only hardware step. You're connecting three things: the MAX485 module to the Pi's GPIO pins, and the MAX485 module to the AquaLogic board.

### 2a. MAX485 to the Raspberry Pi

Use the female-to-female jumper wires. The Pi's pin numbers are printed on the board (or look up "Raspberry Pi Zero 2W pinout" — there are 40 pins in two rows of 20).

| MAX485 Pin | Connect to Pi Pin | What It Does |
|------------|-------------------|-------------|
| VCC | Pin 1 (3.3V power) | Powers the module |
| GND | Pin 6 (Ground) | Ground connection |
| DI | Pin 8 (GPIO14 / UART TX) | Pi sends data to the pool controller |
| DE | Pin 12 (GPIO18) | Tells the module when to transmit |
| RE | Pin 6 (Ground) | Keeps the module always listening (tie to ground) |
| RO | Pin 10 (GPIO15 / UART RX) | Pi receives data from the pool controller |

Yes, both GND and RE go to Pin 6. That's correct — you can use a Y-splitter jumper or daisy-chain them on the same pin.

### 2b. MAX485 to the AquaLogic Board

Open your pool equipment panel. Find the AquaLogic main board — it's labeled **007-243-01** (or similar). Look for a **4-pin header labeled REMOTE DISPLAY** that has nothing plugged into it.

The 4 pins have colored wires on the header (or labeled on the board):

| Remote Display Pin | Wire Color | Connect to MAX485 |
|-------------------|------------|-------------------|
| Pin 1 | RED | **DO NOT CONNECT.** This is +12V and will fry the Pi. |
| Pin 2 | BLACK | MAX485 **B** pin (DATA-) |
| Pin 3 | YELLOW | MAX485 **A** pin (DATA+) |
| Pin 4 | GREEN | MAX485 **GND** |

> **IMPORTANT:** Leave Pin 1 (RED / +12V) completely disconnected. It has nothing to do with your Pi. Connecting it will damage things.

### Sanity check before powering on

- Pi Pin 1 (3.3V) goes to MAX485 VCC — not 5V, not 12V
- Pi Pin 6 (GND) goes to MAX485 GND and MAX485 RE
- Nothing is connected to the red wire on the AquaLogic REMOTE DISPLAY header
- The A and B wires go to the correct side (A = yellow, B = black). If you get these swapped, it won't damage anything, but it won't work — this is the most common mistake

---

## Step 3: Boot the Pi and Connect Over SSH

1. Plug the USB-C power supply into the Pi. Give it about **90 seconds** to boot the first time — it's slow on first boot because it's expanding the filesystem.
2. From your computer (on the same WiFi), open a terminal:
   - **Mac:** Terminal app
   - **Windows:** PowerShell or Command Prompt
   - **Linux:** Any terminal

3. Connect via SSH (this opens a remote terminal session on the Pi over your network):
   ```
   ssh pi@poolcontroller.local
   ```
   Type `yes` when it asks about the fingerprint, then enter the password you set in Step 1.

**If `poolcontroller.local` doesn't work:**
- Wait another minute — the Pi might still be booting.
- Try `ping poolcontroller.local` first. If it says "could not find host," your router might not support mDNS. In that case:
  1. Log into your router's admin page (usually `192.168.1.1`)
  2. Find the DHCP client list / connected devices
  3. Look for a device named `poolcontroller` and note its IP address
  4. Use that IP instead: `ssh pi@192.168.1.XXX`
- On older Windows machines, you may need to install [Bonjour](https://support.apple.com/kb/DL999) for `.local` addresses to work (or just use the IP).

---

## Step 4: Enable the Serial Port

The Pi's serial port is turned off by default. You need to turn it on so it can talk to the MAX485 module.

While SSH'd into the Pi, open the Pi's configuration tool:

```bash
sudo raspi-config
```

This opens a blue menu. Navigate with arrow keys and Enter:

1. Select **Interface Options**
2. Select **Serial Port**
3. "Would you like a login shell over serial?" → **No**
4. "Would you like the serial port hardware to be enabled?" → **Yes**
5. Select **Finish**, then **Yes** to reboot

Wait 30 seconds, then SSH back in:
```
ssh pi@poolcontroller.local
```

Now add two lines to the Pi's boot configuration file. `enable_uart=1` makes sure UART stays enabled across reboots, and `dtoverlay=disable-bt` prevents the Pi's Bluetooth from claiming the serial port you need for RS-485:

```bash
# Append two settings to the boot config file, then restart the Pi
echo -e "enable_uart=1\ndtoverlay=disable-bt" | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

Wait 30 seconds, SSH back in again.

**To verify serial is working** (this checks if the serial port device file exists):
```bash
ls /dev/ttyAMA0
```
If it prints `/dev/ttyAMA0`, you're good. If it says "No such file," the serial port isn't enabled — go through `raspi-config` again.

---

## Step 5: Get the Files onto the Pi

You need to get the project files onto the Pi. Pick whichever method is easiest for you:

### Option A: Download directly on the Pi (easiest)

SSH into the Pi and run:

```bash
cd ~                        # Go to your home folder
curl -L https://github.com/bryanweaver/jareds-pool/archive/refs/heads/main.zip -o pool.zip  # Download the project as a ZIP file
sudo apt install -y unzip   # Install the unzip tool (if not already installed)
unzip pool.zip              # Extract the ZIP file
mv jareds-pool-main jareds-pool  # Rename the extracted folder to something shorter
```

### Option B: Copy files from your computer

If you downloaded the project as a ZIP on your computer (from the green "Code" button on GitHub → "Download ZIP"), unzip it, then from your computer's terminal:

```bash
# Copy the project folder from your computer to the Pi over the network
scp -r /path/to/jareds-pool pi@poolcontroller.local:~/jareds-pool
```

On Windows you can also use [WinSCP](https://winscp.net) — it's a drag-and-drop file transfer app. Connect to `poolcontroller.local` with username `pi` and your password, then drag the project folder into `/home/pi/`.

---

## Step 6: Run the Installer

Now SSH into the Pi (if you aren't already) and run:

```bash
cd ~/jareds-pool          # Go into the project folder
bash scripts/install.sh   # Run the installer script
```

The installer does 5 things automatically:
1. Installs Python dependencies and nginx
2. Copies the bridge program to `/home/pi/pool_bridge.py`
3. Copies the web app to `/var/www/pool/`
4. Configures nginx as a web server
5. Sets up the bridge to start automatically on boot

It takes about 2-3 minutes on a Pi Zero.

**If `curl` or `apt install` fails:** Your Pi might not have internet. Check with `ping google.com`. If that fails, double-check your WiFi credentials from Step 1 (you may need to re-flash the SD card with the correct WiFi name/password).

**If the install script fails with "permission denied":** Make sure you're running it with `bash scripts/install.sh`, not just `./scripts/install.sh`.

---

## Step 7: Verify Everything Is Running

Run these two checks:

```bash
# Ask the system if the pool bridge service is running
sudo systemctl status poolbridge
```

You should see **active (running)** in green. If it says "failed," check the logs:
```bash
# Show the last 30 lines of the bridge's log output
journalctl -u poolbridge -n 30
```

Common issues:
- **"No such file or directory: /dev/ttyAMA0"** — serial port isn't enabled. Go back to Step 4.
- **"ModuleNotFoundError: No module named 'aqualogic'"** — the pip install didn't work. Install the Python library manually: `pip3 install aqualogic --break-system-packages`
- **"Permission denied: /dev/ttyAMA0"** — the Pi user doesn't have permission to use the serial port. Grant access with `sudo usermod -aG dialout pi` (adds the `pi` user to the serial port group), then `sudo reboot`.

Now test the API (this asks the bridge for all current pool data):
```bash
curl http://localhost:4200/state/all
```

If the wiring is correct, you'll see a JSON blob with temperatures, circuit states, salt levels, etc. If you see `{}` (empty), the bridge is running but hasn't received data from the controller yet — check your A/B wiring (try swapping them).

Check nginx too (the web server that serves the app to your browser):
```bash
sudo systemctl status nginx
```

Should also say **active (running)**.

---

## Step 8: Open It on Your Phone

On your phone (connected to the same WiFi as the Pi), open a browser and go to:

```
http://poolcontroller.local
```

You'll see the pool controller app. Tap the status badge at the top to connect. It should auto-detect the Pi and show **Live** in green.

**If the page doesn't load:**
- Try using the Pi's IP address instead: `http://192.168.1.XXX` (find it with `hostname -I` on the Pi)
- Make sure nginx is running: `sudo systemctl status nginx`

**If it loads but says "Offline" or "Connecting":**
- Make sure the bridge is running: `sudo systemctl status poolbridge`
- Try the direct API: open `http://192.168.1.XXX:4200/state/all` in a browser — if that works but the app doesn't, nginx isn't proxying correctly. Run `sudo systemctl restart nginx`.

**If temperatures show but toggles don't work:**
- This usually means the A/B wires are swapped. The Pi can *receive* data on either polarity, but *sending* commands requires the correct wiring. Swap the yellow and black wires at the MAX485.

---

## Step 9 (Optional): Access From Anywhere with Tailscale

Right now this only works on your home WiFi. If you want to check pool temps or toggle the filter from work, the easiest way is Tailscale — it's free and takes 5 minutes.

On the Pi:
```bash
# Download and run the Tailscale installer
curl -fsSL https://tailscale.com/install.sh | sh
# Start Tailscale and register this Pi with your account
sudo tailscale up
```

It will print a URL. Open that URL on your phone or computer, sign in (Google, Microsoft, or GitHub), and approve the Pi.

Then install Tailscale on your phone ([iOS](https://apps.apple.com/app/tailscale/id1470499037) / [Android](https://play.google.com/store/apps/details?id=com.tailscale.ipn)) and sign in with the same account.

Now you can reach your pool controller from anywhere using the Tailscale IP (something like `http://100.x.x.x`). No port forwarding, no exposing anything to the internet.

---

## Day-to-Day Reference

### Useful Commands (via SSH)

| What You Want | Command | What It Does |
|---------------|---------|-------------|
| Check if the bridge is running | `sudo systemctl status poolbridge` | Shows whether the pool bridge service is active or failed |
| View live bridge logs | `journalctl -u poolbridge -f` | Streams log output in real time (press Ctrl+C to stop) |
| Restart the bridge | `sudo systemctl restart poolbridge` | Stops and re-starts the pool bridge service |
| Restart nginx | `sudo systemctl restart nginx` | Stops and re-starts the web server |
| Check the Pi's IP address | `hostname -I` | Prints the Pi's current IP address on your network |
| Test the API manually | `curl http://localhost:4200/state/all` | Fetches all pool data as JSON from the bridge |
| Reboot the Pi | `sudo reboot` | Restarts the entire Pi (takes ~90 seconds to come back) |

### Toggle a Circuit from the Command Line

```bash
# Send a command to the bridge to turn the filter pump on
curl -X PUT http://localhost:4200/state/circuit/setState \
  -H "Content-Type: application/json" \
  -d '{"circuit": "FILTER", "state": true}'
```

The `state` field must be a JSON boolean (`true` or `false`), not a string. `"state": "true"` will be rejected.

Replace `FILTER` with any of these circuit names:
```
FILTER  POOL  SPA  SPILLOVER  LIGHTS  HEATER_1
AUX_1  AUX_2  AUX_3  AUX_4  AUX_5  AUX_6
VALVE_3  VALVE_4  HEATER_AUTO_MODE  FILTER_LOW_SPEED  SUPER_CHLORINATE
```

### API Endpoints

| Endpoint | Method | What It Does |
|----------|--------|-------------|
| `/state/all` | GET | Returns all pool data as JSON (temps, salt, circuits, pump) |
| `/state/circuits` | GET | Returns only circuit on/off states |
| `/state/circuit/setState` | PUT | Toggle a circuit on or off |
| `/events` | GET | Live update stream (Server-Sent Events) |
| `/health` | GET | Is the bridge up and connected? |

The `/state/all` response includes these fields:

| Field | Type | Example |
|-------|------|---------|
| `airTemp` | number | `85` (degrees) |
| `poolTemp` | number | `78` (degrees) |
| `spaTemp` | number | `92` (degrees) |
| `saltLevel` | number | `3200` (PPM) |
| `poolChlorinator` | number | chlorinator % for pool mode |
| `spaChlorinator` | number | chlorinator % for spa mode |
| `pumpSpeed` | number | pump speed (%) |
| `pumpPower` | number | pump power (watts) |
| `isMetric` | boolean | `false` — if `true`, temps are Celsius and salt is g/L |
| `isHeaterEnabled` | boolean | is the heater currently active |
| `checkSystemMsg` | string/null | system warning message, if any |
| `circuits` | object | `{"FILTER": true, "LIGHTS": false, ...}` |

---

## Troubleshooting

### "I can't SSH into the Pi"
- Is it powered on? The green LED should blink occasionally.
- Is it on the same WiFi? Double-check the WiFi name/password you set in Raspberry Pi Imager.
- Wait 2 full minutes on first boot before trying.
- Try the IP address instead of `poolcontroller.local` (check your router's device list).

### "The bridge starts but shows no data"
- The most common cause is swapped A/B wires. Try swapping the yellow and black wires at the MAX485 module.
- Make sure GND from the AquaLogic REMOTE DISPLAY port (green wire, Pin 4) is connected to MAX485 GND.
- Verify the serial port is `/dev/ttyAMA0` by running `ls /dev/ttyAMA0`.

### "Everything worked yesterday but stopped"
- Power outage? The bridge auto-starts on boot, but the Pi needs ~90 seconds to come up.
- Check `sudo systemctl status poolbridge` — if it says "failed," restart it with `sudo systemctl restart poolbridge`.
- Check `journalctl -u poolbridge -n 50` for error messages.
- WiFi flaky? Run `ping google.com` — if it fails, the Pi lost its WiFi connection. `sudo reboot` usually fixes it.

### "The app loads but I see Demo Mode"
- The app starts in Demo Mode when it can't reach the bridge. Demo mode shows fake data so you can preview the interface — toggles will appear to work but aren't sending real commands.
- To connect to your real pool: tap the status badge at the top of the app and enter the Pi's address. If you accessed the app via `poolcontroller.local`, it should auto-connect. If not, enter the Pi's IP address and port 4200.

### "I want to update the software"
Delete the old folder and re-download it (same as Step 5), then re-run the installer:
```bash
cd ~                        # Go to your home folder
rm -rf jareds-pool          # Delete the old project folder
curl -L https://github.com/bryanweaver/jareds-pool/archive/refs/heads/main.zip -o pool.zip  # Download the latest version
unzip -o pool.zip           # Extract it (overwrite if needed)
mv jareds-pool-main jareds-pool  # Rename the folder
cd jareds-pool              # Go into the project folder
bash scripts/install.sh     # Re-run the installer
```

---

## How It Works (The Short Version)

The AquaLogic controller has an unused **REMOTE DISPLAY** port that speaks RS-485 — a simple two-wire serial protocol. The MAX485 module converts that to the kind of serial signal the Pi's GPIO pins understand.

A Python program (`pool_bridge.py`) reads data from the controller, converts it to JSON, and serves it as an HTTP API on port 4200. It also accepts commands to toggle circuits.

Nginx sits in front as a web server — it serves the HTML interface and forwards API requests to the bridge.

The web app (`index.html`) is a single HTML file with no dependencies. It connects to the API, shows you live data via Server-Sent Events, and sends toggle commands when you tap a button. It also includes a built-in interactive setup guide — open the app and look for the setup accordion if you need a refresher on wiring or configuration.

---

## Built With

- [aqualogic](https://github.com/swilson/aqualogic) — Python library for the Hayward RS-485 protocol
- Vanilla HTML/CSS/JS — no frameworks, no build step, no npm

## Compatibility

Tested with Hayward AquaLogic (board 007-243-01). Should also work with ProLogic controllers that use the same RS-485 protocol.

## License

MIT
