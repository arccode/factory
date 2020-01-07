# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

r"""Utility functions to mock SCPI device over TCP.

Example Usage:
  MockServerHandler.AddLookup(r'\*CLS', None)
  SetupLookupTable()
  SERVER_PORT = 5025
  MockTestServer(('0.0.0.0', SERVER_PORT), MockServerHandler).serve_forever()
"""

import inspect
import logging
import re
import socketserver


class MockTestServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
  allow_reuse_address = True


class MockServerHandler(socketserver.StreamRequestHandler):
  """A mocking handler for socket.

  This handler responses client based on its pre-defined lookup table.
  Lookup table is a list of tuple where the first of each tuple is a regular
  expression and the second is response. Response could be one of None, string
  or function.

  Exceptions will be raised if input cannot match any of the regular expression
  from keys.
  """
  responses_lookup = []

  @classmethod
  def AddLookup(cls, input_line, response):
    # Check if the response is one of the known types.
    is_known_types = False
    if isinstance(response, (bytes, type(None))):
      is_known_types = True
    elif inspect.isfunction(response) or inspect.ismethod(response):
      is_known_types = True
    assert is_known_types, (
        'type %r of response is not supported' % type(response))
    cls.responses_lookup.append((input_line, response))

  def __init__(self, *args, **kwargs):
    self.lookup = list(self.responses_lookup)
    socketserver.StreamRequestHandler.__init__(self, *args, **kwargs)

  def handle(self):
    while True:
      line = self.rfile.readline().rstrip('\r\n')
      if not line:
        break
      matched = False
      for regexp, response in self.lookup:
        if not re.search(regexp, line):
          continue
        matched = True
        logging.info('Input %r matched with regexp %r', line, regexp)
        if inspect.isfunction(response) or inspect.ismethod(response):
          response = response(line)

        if isinstance(response, bytes):
          self.wfile.write(response)
        elif isinstance(response, type(None)):
          pass
        # Only the first match will be used.
        break
      if not matched:
        raise ValueError('Input %r is not matching any.' % line)
