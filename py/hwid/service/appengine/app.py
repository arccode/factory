#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The service handler for APIs."""

import logging

# pylint: disable=no-name-in-module, import-error, wrong-import-order
import flask
import google.cloud.logging as gc_logging
# pylint: enable=no-name-in-module, import-error, wrong-import-order

from cros.factory.hwid.service.appengine import auth
from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import hwid_api
from cros.factory.hwid.service.appengine import ingestion
from cros.factory.probe_info_service.app_engine import protorpc_utils


def _CreateApp():
  app = flask.Flask(__name__)
  app.url_map.strict_slashes = False

  app.add_url_rule(
      rule='/ingestion/sync_name_pattern', endpoint='sync_name_pattern',
      view_func=auth.HttpCheck(
          ingestion.SyncNamePatternHandler.as_view('sync_name_pattern')))
  app.add_url_rule(
      rule='/ingestion/refresh', endpoint='refresh', view_func=auth.HttpCheck(
          ingestion.RefreshHandler.as_view('refresh')))
  app.add_url_rule(
      rule='/ingestion/all_devices_refresh', endpoint='all_devices_refresh',
      view_func=auth.HttpCheck(
          ingestion.AllDevicesRefreshHandler.as_view('all_devices_refresh')))

  protorpc_utils.RegisterProtoRPCServiceToFlaskApp(app, '/_ah/stubby',
                                                   hwid_api.ProtoRPCService())
  return app


def _InitLogging():
  if CONFIG.cloud_project:  # in App Engine environment
    client = gc_logging.Client()
    handler = gc_logging.handlers.AppEngineHandler(client)
    gc_logging.handlers.setup_logging(handler, log_level=logging.DEBUG)
  else:
    logging.basicConfig(level=logging.DEBUG)


_InitLogging()
hwid_service = _CreateApp()


if __name__ == '__main__':
  hwid_service.run(debug=True)
