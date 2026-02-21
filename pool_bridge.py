#!/usr/bin/env python3
"""
Pool Bridge — AquaLogic RS-485 → REST API + WebSocket
Runs on Raspberry Pi Zero 2W with MAX485 module connected to
the Hayward AquaLogic REMOTE DISPLAY port.

API:
  GET  /state/all              → full state JSON
  PUT  /state/circuit/setState  → {"circuit":"FILTER","state":true}
  GET  /ws                     → WebSocket (live state push)
"""

import json, threading, queue, time, logging, signal, sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from aqualogic.core import AquaLogic
from aqualogic.states import States

# ─── Config ────────────────────────────────────────────────────────
SERIAL_PORT = '/dev/ttyAMA0'
HTTP_PORT   = 4200
LOG_LEVEL   = logging.INFO

# ─── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('pool_bridge')

# ─── Circuit map (state name → States enum) ───────────────────────
CIRCUIT_MAP = {
    'FILTER':    States.FILTER,
    'POOL':      States.POOL,
    'SPA':       States.SPA,
    'SPILLOVER': States.SPILLOVER,
    'LIGHTS':    States.LIGHTS,
    'HEATER_1':  States.HEATER_1,
    'AUX_1':     States.AUX_1,
    'AUX_2':     States.AUX_2,
    'AUX_3':     States.AUX_3,
    'AUX_4':     States.AUX_4,
    'AUX_5':     States.AUX_5,
    'AUX_6':     States.AUX_6,
    'VALVE_3':   States.VALVE_3,
    'VALVE_4':   States.VALVE_4,
    'HEATER_AUTO_MODE': States.HEATER_AUTO_MODE,
    'SUPER_CHLORINATE': States.SUPER_CHLORINATE,
    'FILTER_LOW_SPEED': States.FILTER_LOW_SPEED,
}

# ─── Shared state ─────────────────────────────────────────────────
panel = None          # AquaLogic instance (set after connect)
state_lock = threading.Lock()
current_state = {}    # latest JSON-serializable state
ws_clients = set()    # simple polling set (SSE-style)
state_version = 0     # incremented on every state change

def build_state(p):
    """Build a JSON-serializable dict from the AquaLogic panel."""
    circuits = {}
    for name, s in CIRCUIT_MAP.items():
        try:
            circuits[name] = p.get_state(s)
        except Exception:
            circuits[name] = False

    return {
        'airTemp':          p.air_temp,
        'poolTemp':         p.pool_temp,
        'spaTemp':          p.spa_temp,
        'saltLevel':        p.salt_level,
        'poolChlorinator':  p.pool_chlorinator,
        'spaChlorinator':   p.spa_chlorinator,
        'pumpSpeed':        p.pump_speed,
        'pumpPower':        p.pump_power,
        'isMetric':         p.is_metric,
        'isHeaterEnabled':  p.is_heater_enabled,
        'checkSystemMsg':   p.check_system_msg,
        'circuits':         circuits,
    }

def on_data_changed(p):
    """Callback from AquaLogic when any data changes."""
    global current_state, state_version
    new_state = build_state(p)
    with state_lock:
        current_state = new_state
        state_version += 1
    log.debug('State updated: air=%s pool=%s spa=%s',
              new_state.get('airTemp'), new_state.get('poolTemp'),
              new_state.get('spaTemp'))

# ─── HTTP Server (runs in its own thread) ─────────────────────────
class PoolHandler(BaseHTTPRequestHandler):
    """Minimal REST API handler."""

    def log_message(self, format, *args):
        log.debug('HTTP %s', format % args)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, PUT, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json_response(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/state/all':
            with state_lock:
                data = dict(current_state)
            self._json_response(data)

        elif self.path == '/state/circuits':
            with state_lock:
                data = current_state.get('circuits', {})
            self._json_response(data)

        elif self.path.startswith('/ws') or self.path == '/events':
            # Server-Sent Events stream (simple alternative to WebSocket)
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self._cors()
            self.end_headers()
            last_version = 0
            try:
                while True:
                    if state_version != last_version:
                        with state_lock:
                            data = json.dumps(current_state)
                        last_version = state_version
                        self.wfile.write(f'data: {data}\n\n'.encode())
                        self.wfile.flush()
                    time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError):
                pass

        elif self.path == '/health':
            self._json_response({'ok': True, 'connected': panel is not None})

        else:
            self._json_response({'error': 'not found'}, 404)

    def do_PUT(self):
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len)
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._json_response({'error': 'invalid JSON'}, 400)
            return

        if self.path == '/state/circuit/setState':
            circuit_name = data.get('circuit', '').upper()
            desired = data.get('state', True)

            if circuit_name not in CIRCUIT_MAP:
                self._json_response({
                    'error': f'Unknown circuit: {circuit_name}',
                    'validCircuits': list(CIRCUIT_MAP.keys())
                }, 400)
                return

            if panel is None:
                self._json_response({'error': 'Not connected to controller'}, 503)
                return

            try:
                result = panel.set_state(CIRCUIT_MAP[circuit_name], bool(desired))
                self._json_response({'ok': result, 'circuit': circuit_name, 'state': desired})
            except Exception as e:
                log.error('set_state error: %s', e)
                self._json_response({'error': str(e)}, 500)

        else:
            self._json_response({'error': 'not found'}, 404)

def run_http_server():
    server = HTTPServer(('0.0.0.0', HTTP_PORT), PoolHandler)
    server.timeout = 1
    log.info('HTTP server listening on port %d', HTTP_PORT)
    while True:
        server.handle_request()

# ─── AquaLogic process loop (runs in main thread) ─────────────────
def run_aqualogic():
    global panel
    while True:
        try:
            log.info('Connecting to AquaLogic on %s...', SERIAL_PORT)
            panel = AquaLogic(web_port=0)  # disable built-in web server
            panel.connect_serial(SERIAL_PORT)
            log.info('Connected. Processing RS-485 data...')
            panel.process(on_data_changed)
            log.warning('AquaLogic process() returned (serial timeout or EOF)')
        except Exception as e:
            log.error('AquaLogic error: %s', e)
        panel = None
        log.info('Reconnecting in 5 seconds...')
        time.sleep(5)

# ─── Main ──────────────────────────────────────────────────────────
def main():
    log.info('=== Pool Bridge starting ===')
    log.info('Serial: %s  |  HTTP: %d', SERIAL_PORT, HTTP_PORT)

    # Start HTTP server in background thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    # Run AquaLogic in main thread (blocking)
    run_aqualogic()

if __name__ == '__main__':
    main()
