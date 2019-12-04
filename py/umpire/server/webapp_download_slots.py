# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire download slots web application.

The class handles 'http://umpire_address:umpire_port/webapps/download_slots'
HTTP GET.
"""

import logging

from cros.factory.umpire.server import download_slots_manager
from cros.factory.umpire.server.web import wsgi
from cros.factory.umpire.server import webapp_utils


PATH_INFO = '/webapps/download_slots'


class DownloadSlotsApp(wsgi.WebApp):
  """Download slots web application class."""

  def __init__(self):
    self._manager = download_slots_manager.DownloadSlotsManager()

  def Handle(self, session):
    """Gets resource map from DUT info and return text/plain result."""
    logging.debug('download_slots app: %s', session)
    if session.REQUEST_METHOD == 'GET':
      dut_info = webapp_utils.ParseDUTHeader(session.HTTP_X_UMPIRE_DUT)
      result = self._manager.ProcessSlotRequest(dut_info)
      if result:
        return session.Respond(result)
    return session.BadRequest400()
