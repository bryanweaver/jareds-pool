"""
Critical tests for pool_bridge.py

Covers the 4 disaster-prevention scenarios:
1. Boolean coercion — string "false" must NOT be treated as True
2. Thread-safety — panel going None mid-request must not crash
3. Malformed Content-Length — must return 400, not crash handler
4. SSE connection cleanup — OSError variants must be caught
"""

import json
import io
import threading
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

# Mock aqualogic before importing pool_bridge
import sys
mock_aqualogic_core = MagicMock()
mock_aqualogic_states = MagicMock()
# Create real enum-like values for States
for name in [
    'FILTER', 'POOL', 'SPA', 'SPILLOVER', 'LIGHTS', 'HEATER_1',
    'AUX_1', 'AUX_2', 'AUX_3', 'AUX_4', 'AUX_5', 'AUX_6',
    'VALVE_3', 'VALVE_4', 'HEATER_AUTO_MODE', 'SUPER_CHLORINATE',
    'FILTER_LOW_SPEED',
]:
    setattr(mock_aqualogic_states.States, name, name)

sys.modules['aqualogic'] = MagicMock()
sys.modules['aqualogic.core'] = mock_aqualogic_core
sys.modules['aqualogic.states'] = mock_aqualogic_states

import pool_bridge
from pool_bridge import PoolHandler


def make_handler(method, path, body=None, headers=None):
    """Create a PoolHandler with a fake request/response."""
    handler = PoolHandler.__new__(PoolHandler)
    handler.command = method
    handler.path = path
    handler.headers = {}
    handler.request_version = 'HTTP/1.1'

    # Response buffer
    handler.wfile = io.BytesIO()
    handler._headers_buffer = []

    # Override response methods to capture output
    handler._response_code = None
    handler._response_body = None
    handler._sent_headers = {}

    original_json_response = PoolHandler._json_response

    def capture_json_response(self, data, code=200):
        self._response_code = code
        self._response_body = data
    handler._json_response = capture_json_response.__get__(handler, PoolHandler)

    # Set up request body
    if body is not None:
        raw = json.dumps(body).encode() if isinstance(body, dict) else body
        handler.rfile = io.BytesIO(raw)
        handler.headers = {'Content-Length': str(len(raw))}
    else:
        handler.rfile = io.BytesIO(b'')
        handler.headers = {}

    # Override headers if specified
    if headers is not None:
        handler.headers.update(headers)

    # Make headers dict-like with .get()
    class HeaderDict(dict):
        def get(self, key, default=None):
            return super().get(key, default)
    handler.headers = HeaderDict(handler.headers)

    return handler


class TestBooleanCoercion(unittest.TestCase):
    """CRITICAL GAP 1: String "false" must not be treated as True."""

    @patch.object(pool_bridge, 'panel')
    def test_string_false_rejected(self, mock_panel):
        """PUT with state:"false" (string) must return 400, not toggle ON."""
        mock_panel.set_state = MagicMock(return_value=True)

        handler = make_handler('PUT', '/state/circuit/setState',
                               body={'circuit': 'FILTER', 'state': 'false'})
        handler.do_PUT()

        self.assertEqual(handler._response_code, 400)
        mock_panel.set_state.assert_not_called()

    @patch.object(pool_bridge, 'panel')
    def test_string_true_rejected(self, mock_panel):
        """PUT with state:"true" (string) must return 400."""
        mock_panel.set_state = MagicMock(return_value=True)

        handler = make_handler('PUT', '/state/circuit/setState',
                               body={'circuit': 'FILTER', 'state': 'true'})
        handler.do_PUT()

        self.assertEqual(handler._response_code, 400)
        mock_panel.set_state.assert_not_called()

    @patch.object(pool_bridge, 'panel')
    def test_integer_state_rejected(self, mock_panel):
        """PUT with state:1 (integer) must return 400."""
        mock_panel.set_state = MagicMock(return_value=True)

        handler = make_handler('PUT', '/state/circuit/setState',
                               body={'circuit': 'FILTER', 'state': 1})
        handler.do_PUT()

        self.assertEqual(handler._response_code, 400)
        mock_panel.set_state.assert_not_called()

    @patch.object(pool_bridge, 'panel')
    def test_bool_true_accepted(self, mock_panel):
        """PUT with state:true (boolean) must be accepted."""
        mock_panel.set_state = MagicMock(return_value=True)

        handler = make_handler('PUT', '/state/circuit/setState',
                               body={'circuit': 'FILTER', 'state': True})
        handler.do_PUT()

        self.assertEqual(handler._response_code, 200)
        mock_panel.set_state.assert_called_once()

    @patch.object(pool_bridge, 'panel')
    def test_bool_false_accepted(self, mock_panel):
        """PUT with state:false (boolean) must be accepted."""
        mock_panel.set_state = MagicMock(return_value=True)

        handler = make_handler('PUT', '/state/circuit/setState',
                               body={'circuit': 'FILTER', 'state': False})
        handler.do_PUT()

        self.assertEqual(handler._response_code, 200)
        mock_panel.set_state.assert_called_once()


class TestPanelThreadSafety(unittest.TestCase):
    """CRITICAL GAP 2: Panel going None mid-request must not crash."""

    def test_panel_none_returns_503(self):
        """PUT when panel is None must return 503."""
        with patch.object(pool_bridge, 'panel', None):
            handler = make_handler('PUT', '/state/circuit/setState',
                                   body={'circuit': 'FILTER', 'state': True})
            handler.do_PUT()

        self.assertEqual(handler._response_code, 503)

    def test_panel_set_state_exception_returns_500(self):
        """If panel.set_state raises, must return 500 (not crash thread)."""
        mock_panel = MagicMock()
        mock_panel.set_state.side_effect = AttributeError("'NoneType' object has no attribute 'set_state'")

        with patch.object(pool_bridge, 'panel', mock_panel):
            handler = make_handler('PUT', '/state/circuit/setState',
                                   body={'circuit': 'FILTER', 'state': True})
            handler.do_PUT()

        self.assertEqual(handler._response_code, 500)

    def test_panel_set_state_oserror_returns_500(self):
        """If panel.set_state raises OSError (serial disconnect), must return 500."""
        mock_panel = MagicMock()
        mock_panel.set_state.side_effect = OSError("serial port disconnected")

        with patch.object(pool_bridge, 'panel', mock_panel):
            handler = make_handler('PUT', '/state/circuit/setState',
                                   body={'circuit': 'FILTER', 'state': True})
            handler.do_PUT()

        self.assertEqual(handler._response_code, 500)


class TestContentLengthValidation(unittest.TestCase):
    """CRITICAL GAP 3: Bad Content-Length must not crash the handler."""

    def test_invalid_content_length_returns_400(self):
        """Content-Length: 'abc' must return 400, not ValueError crash."""
        handler = make_handler('PUT', '/state/circuit/setState',
                               headers={'Content-Length': 'abc'})
        handler.rfile = io.BytesIO(b'{}')

        # This must not raise ValueError
        handler.do_PUT()

        self.assertEqual(handler._response_code, 400)

    def test_empty_content_length_returns_400(self):
        """Content-Length: '' (empty) must return 400."""
        handler = make_handler('PUT', '/state/circuit/setState',
                               headers={'Content-Length': ''})
        handler.rfile = io.BytesIO(b'{}')

        handler.do_PUT()

        self.assertEqual(handler._response_code, 400)

    def test_negative_content_length_returns_400(self):
        """Content-Length: -1 must return 400."""
        handler = make_handler('PUT', '/state/circuit/setState',
                               headers={'Content-Length': '-1'})
        handler.rfile = io.BytesIO(b'{}')

        handler.do_PUT()

        self.assertEqual(handler._response_code, 400)

    def test_oversized_content_length_returns_413(self):
        """Content-Length > max allowed must return 413."""
        handler = make_handler('PUT', '/state/circuit/setState',
                               headers={'Content-Length': '10000000'})
        handler.rfile = io.BytesIO(b'{}')

        handler.do_PUT()

        self.assertIn(handler._response_code, [400, 413])

    def test_missing_content_length_uses_zero(self):
        """Missing Content-Length must default to 0, returning 400 for missing fields."""
        handler = make_handler('PUT', '/state/circuit/setState')
        handler.headers = make_handler.__code__ and type(handler.headers)({})

        handler.do_PUT()

        # With no body, circuit_name will be '' which is not in CIRCUIT_MAP → 400
        self.assertEqual(handler._response_code, 400)

    @patch.object(pool_bridge, 'panel')
    def test_valid_content_length_works(self, mock_panel):
        """Normal request with valid Content-Length must succeed."""
        mock_panel.set_state = MagicMock(return_value=True)

        handler = make_handler('PUT', '/state/circuit/setState',
                               body={'circuit': 'FILTER', 'state': True})
        handler.do_PUT()

        self.assertEqual(handler._response_code, 200)


class TestSSEErrorHandling(unittest.TestCase):
    """CRITICAL GAP 4: SSE must catch all connection errors."""

    def test_oserror_caught_in_sse(self):
        """OSError during SSE write must be caught (not just BrokenPipe)."""
        handler = PoolHandler.__new__(PoolHandler)
        handler.path = '/events'
        handler.command = 'GET'
        handler.request_version = 'HTTP/1.1'
        handler._headers_buffer = []

        # Mock wfile that raises OSError on write
        mock_wfile = MagicMock()

        call_count = 0
        def send_response_side_effect(code):
            nonlocal call_count
            call_count += 1

        handler.send_response = send_response_side_effect
        handler.send_header = MagicMock()
        handler._cors = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = mock_wfile

        # Set state_version so SSE tries to write immediately
        original_version = pool_bridge.state_version
        pool_bridge.state_version = original_version + 1

        # OSError (not BrokenPipe or ConnectionReset) should also be caught
        mock_wfile.write.side_effect = OSError(104, "Connection reset by peer")

        try:
            handler.do_GET()
        except OSError:
            self.fail("OSError was not caught in SSE handler - thread would leak!")
        finally:
            pool_bridge.state_version = original_version


class TestCircuitValidation(unittest.TestCase):
    """Bonus: Unknown circuit names must be rejected."""

    @patch.object(pool_bridge, 'panel')
    def test_unknown_circuit_rejected(self, mock_panel):
        """PUT with unknown circuit name must return 400."""
        handler = make_handler('PUT', '/state/circuit/setState',
                               body={'circuit': 'NONEXISTENT', 'state': True})
        handler.do_PUT()

        self.assertEqual(handler._response_code, 400)
        self.assertIn('validCircuits', handler._response_body)

    def test_invalid_json_returns_400(self):
        """PUT with invalid JSON body must return 400."""
        handler = make_handler('PUT', '/state/circuit/setState',
                               body=b'not json at all')
        handler.headers = type(handler.headers)({'Content-Length': '15'})
        handler.rfile = io.BytesIO(b'not json at all')

        handler.do_PUT()

        self.assertEqual(handler._response_code, 400)

    def test_unknown_path_returns_404(self):
        """PUT to unknown path must return 404."""
        handler = make_handler('PUT', '/nonexistent',
                               body={'foo': 'bar'})
        handler.do_PUT()

        self.assertEqual(handler._response_code, 404)


class TestHealthEndpoint(unittest.TestCase):
    """Health check must reflect actual connection state."""

    def test_health_when_disconnected(self):
        """Health check with panel=None must report connected=False."""
        handler = PoolHandler.__new__(PoolHandler)
        handler.path = '/health'
        handler.command = 'GET'
        handler.request_version = 'HTTP/1.1'
        handler._response_code = None
        handler._response_body = None

        def capture(data, code=200):
            handler._response_code = code
            handler._response_body = data
        handler._json_response = capture

        with patch.object(pool_bridge, 'panel', None):
            handler.do_GET()

        self.assertEqual(handler._response_code, 200)
        self.assertFalse(handler._response_body['connected'])

    def test_health_when_connected(self):
        """Health check with active panel must report connected=True."""
        handler = PoolHandler.__new__(PoolHandler)
        handler.path = '/health'
        handler.command = 'GET'
        handler.request_version = 'HTTP/1.1'
        handler._response_code = None
        handler._response_body = None

        def capture(data, code=200):
            handler._response_code = code
            handler._response_body = data
        handler._json_response = capture

        mock_panel = MagicMock()
        with patch.object(pool_bridge, 'panel', mock_panel):
            handler.do_GET()

        self.assertEqual(handler._response_code, 200)
        self.assertTrue(handler._response_body['connected'])


if __name__ == '__main__':
    unittest.main()
