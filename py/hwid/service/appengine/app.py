# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The service handler for APIs."""

import os

# pylint: disable=no-name-in-module, import-error, wrong-import-order
import endpoints
import google.cloud.logging as gc_logging
import webapp2
# pylint: enable=no-name-in-module, import-error, wrong-import-order

from cros.factory.hwid.service.appengine import goldeneye_ingestion
from cros.factory.hwid.service.appengine import hwid_api
from cros.factory.hwid.service.appengine import ingestion


hwid_api_app = endpoints.api_server([hwid_api.HwidApi], restricted=True)
ingestion_app = webapp2.WSGIApplication(
    [
        ('/ingestion/upload', ingestion.DevUploadHandler),
        ('/ingestion/refresh', ingestion.RefreshHandler),
        ('/ingestion/sync_name_pattern', ingestion.SyncNamePatternHandler),
        ('/ingestion/all_devices_refresh',
         goldeneye_ingestion.AllDevicesRefreshHandler),
    ],
    debug=False)


def _InitLogging():
  if os.environ.get('IS_APPENGINE') == 'true':
    client = gc_logging.Client()
    client.get_default_handler()
    client.setup_logging()


_InitLogging()
