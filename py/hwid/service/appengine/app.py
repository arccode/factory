#!/usr/bin/env python3
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The service handler for APIs."""

import functools
import http
import logging

# pylint: disable=no-name-in-module, import-error, wrong-import-order
import flask
import google.cloud.logging as gc_logging
# pylint: enable=no-name-in-module, import-error, wrong-import-order

from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import goldeneye_ingestion
from cros.factory.hwid.service.appengine import hwid_api
from cros.factory.hwid.service.appengine import ingestion

def _AuthCheck():
  if CONFIG.env == 'dev':  # for integration test
    return

  from_cron = flask.request.headers.get('X-AppEngine-Cron')
  if from_cron:
    logging.info('Allow cron job requests')
    return

  from_cloud_task = flask.request.headers.get('X-AppEngine-QueueName')
  if from_cloud_task:
    logging.info('Allow cloud task requests')
    return

  if CONFIG.ingestion_api_key:
    key = flask.request.args.get('key')
    if key == CONFIG.ingestion_api_key:
      logging.info('Allow normal requests with API key')
      return

  flask.abort(http.HTTPStatus.FORBIDDEN)


def _AuthCheckWrapper(func):
  """Checks if requests are from known source.

  For /ingestion/refresh  and /ingestion/sync_name_pattern API, hwid service
  only allows cron job (via GET) and cloud task (via POST) requests.  However,
  for e2e testing purpose, requests with API key are also allowed.
  """
  @functools.wraps(func)
  def wrapper(*args, **kwargs):
    _AuthCheck()
    return func(*args, **kwargs)
  return wrapper


def _CreateApp():
  app = flask.Flask(__name__)
  app.url_map.strict_slashes = False

  app.add_url_rule(
      rule='/ingestion/upload', endpoint='upload',
      view_func=ingestion.DevUploadHandler.as_view('upload'))
  app.add_url_rule(
      rule='/ingestion/sync_name_pattern', endpoint='sync_name_pattern',
      view_func=ingestion.SyncNamePatternHandler.as_view('sync_name_pattern'))
  app.add_url_rule(
      rule='/ingestion/refresh', endpoint='refresh',
      view_func=_AuthCheckWrapper(ingestion.RefreshHandler.as_view('refresh')))
  app.add_url_rule(
      rule='/ingestion/all_devices_refresh', endpoint='all_devices_refresh',
      view_func=_AuthCheckWrapper(
          goldeneye_ingestion.AllDevicesRefreshHandler.as_view(
              'all_devices_refresh')))
  hwid_api.bp.before_request(_AuthCheck)
  app.register_blueprint(hwid_api.bp)
  return app


def _InitLogging():
  if CONFIG.cloud_project:  # in App Engine environment
    client = gc_logging.Client()
    client.get_default_handler()
    client.setup_logging()
  else:
    logging.basicConfig(level=logging.DEBUG)


_InitLogging()
hwid_service = _CreateApp()


if __name__ == '__main__':
  hwid_service.run(debug=True)
