# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# pylint: disable=no-member

"""Umpire download slots web application.

The class handles 'http://umpire_address:umpire_port/webapps/download_slots'
HTTP GET.
"""

import logging

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire.server import download_slots_manager
from cros.factory.umpire.server.web import wsgi
from cros.factory.umpire.server import webapp_utils
from cros.factory.utils import type_utils


_PATH_INFO = '/webapps/download_slots'


class DownloadSlotsApp(object):
  """Web application callable class.

  Args:
    env: UmpireEnv object.
  """

  def __init__(self, env):
    self.env = env
    self.manager = download_slots_manager.DownloadSlotsManager()

  def __call__(self, environ, start_response):
    """Gets resource map from DUT info and return text/plain result."""
    session = wsgi.WSGISession(environ, start_response)
    logging.debug('download_slots app: %s', session)
    if session.REQUEST_METHOD == 'GET':
      dut_info = webapp_utils.ParseDUTHeader(session.HTTP_X_UMPIRE_DUT)
      result = self.manager.ProcessSlotRequest(dut_info)
      if result:
        return session.Respond(type_utils.UnicodeToString(result))
    return session.BadRequest400()

  def GetPathInfo(self):
    return _PATH_INFO
