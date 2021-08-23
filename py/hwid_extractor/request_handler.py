# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""A tool to quickly extract HWID and serial no. from DUT."""

import http
from http import server as http_server
import json
import logging
import os
import traceback
from urllib import parse as urlparse

from cros.factory.hwid_extractor import ap_firmware
from cros.factory.hwid_extractor import device


WWW_ROOT_DIR = os.path.join(os.path.dirname(__file__), 'www')
CONFIG_JSON = os.path.join(WWW_ROOT_DIR, 'config.json')


class APIError(Exception):

  def __init__(self, message, status_code):
    super().__init__()
    self.message = message
    self.status_code = status_code


class RequestHandler(http_server.SimpleHTTPRequestHandler):
  """Implementation of the request handler."""

  def __init__(self, *args, **kargs):
    #TODO(chungsheng): Use argument `directory` after python3.7
    os.chdir(WWW_ROOT_DIR)
    super().__init__(*args, **kargs)
    self._params = {}

  def _SendJSON(self, data, status=http.HTTPStatus.OK):
    """Send JSON result to client."""
    logging.info('server response: %s', data)
    body = json.dumps(data).encode()
    self.send_response(status)
    self.send_header('Content-Type', 'application/json')
    self.send_header('Content-Length', len(body))
    self.send_header('Access-Control-Allow-Origin', '*')
    self.end_headers()
    self.wfile.write(body)

  def _SendActionResult(self, result):
    """Send a boolean value 'success' for the result of the action."""
    self._SendJSON({'success': bool(result)})

  def _ParseJSONPayload(self):
    if self.headers.get('Content-Type') != 'application/json':
      raise APIError('Only accept json as post payload.',
                     http.HTTPStatus.BAD_REQUEST)
    length = int(self.headers.get('Content-Length'))
    return json.loads(self.rfile.read(length))

  def _GetArgument(self, arg_name):
    """Get argument and send error when argument is missing."""
    arg = self._params.get(arg_name)
    if not arg:
      raise APIError(f'Argument {arg_name!r} is required.',
                     http.HTTPStatus.BAD_REQUEST)
    return arg

  def _Scan(self):
    """Find a device. Return the status of the device if found."""
    self._SendJSON(device.Scan())

  def _Lock(self):
    cr50_serial_name = self._GetArgument('cr50SerialName')
    self._SendActionResult(device.Lock(cr50_serial_name))

  def _Unlock(self):
    cr50_serial_name = self._GetArgument('cr50SerialName')
    authcode = self._GetArgument('authcode')
    self._SendActionResult(device.Unlock(cr50_serial_name, authcode))

  def _Extract(self):
    """Extract HWID and SN."""
    cr50_serial_name = self._GetArgument('cr50SerialName')
    board = self._GetArgument('board')
    hwid, serial_number = device.ExtractHWIDAndSerialNumber(
        cr50_serial_name, board)
    self._SendJSON({
        'hwid': hwid,
        'sn': serial_number,
    })

  def _UpdateRLZ(self):
    all_device = self._params
    self._SendActionResult(device.RLZ_DATA.UpdateFromAllDevicesJSON(all_device))

  def _UpdateConfig(self):
    """Save the extractor config file to config.json."""
    config = self._params
    with open(CONFIG_JSON, 'w') as f:
      json.dump(config, f)
    self._SendActionResult(True)

  def _EnableTestlab(self):
    cr50_serial_name = self._GetArgument('cr50SerialName')
    self._SendActionResult(device.EnableTestlab(cr50_serial_name))

  def _DisableTestlab(self):
    cr50_serial_name = self._GetArgument('cr50SerialName')
    self._SendActionResult(device.DisableTestlab(cr50_serial_name))

  def _GetSupportedBoards(self):
    self._SendJSON({'supportedBoards': ap_firmware.GetSupportedBoards()})

  def do_POST(self):
    """Overwrite the parent's do_POST method."""
    try:
      path = urlparse.urlparse(self.path).path
      self._params = self._ParseJSONPayload()
      logging.info('POST %s, params: %s', path, self._params)
      if path == '/scan':
        self._Scan()
      elif path == '/lock':
        self._Lock()
      elif path == '/unlock':
        self._Unlock()
      elif path == '/extract':
        self._Extract()
      elif path == '/update-rlz':
        self._UpdateRLZ()
      elif path == '/update-config':
        self._UpdateConfig()
      elif path == '/testlab-enable':
        self._EnableTestlab()
      elif path == '/testlab-disable':
        self._DisableTestlab()
      elif path == '/get-supported-boards':
        self._GetSupportedBoards()
      else:
        self._SendJSON({
            'error': 'Not found',
        }, http.HTTPStatus.NOT_FOUND)
    except APIError as e:
      self._SendJSON({
          'error': e.message,
      }, e.status_code)
    except Exception as e:
      self._SendJSON({
          'error': repr(e),
          'traceback': traceback.format_exc()
      }, http.HTTPStatus.INTERNAL_SERVER_ERROR)
      raise
