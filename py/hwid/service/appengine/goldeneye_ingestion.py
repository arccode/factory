# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handler that ingests the latest all_devices.json from GoldenEye."""

import http
import json
import logging

# pylint: disable=no-name-in-module, import-error, wrong-import-order
import flask
import flask.views
from google.cloud import tasks
# pylint: enable=no-name-in-module, import-error, wrong-import-order

from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import memcache_adapter
from cros.factory.hwid.v3 import filesystem_adapter


MEMCACHE_NAMESPACE = 'SourceGoldenEye'


class AllDevicesRefreshHandler(flask.views.MethodView):
  """Handle update of a possibly new all_devices.json file."""

  # Cron jobs are always GET requests, we are not actually doing the work
  # here just queuing a task to be run in the background.
  def get(self):
    client = tasks.CloudTasksClient()
    parent = client.queue_path(CONFIG.cloud_project, CONFIG.project_region,
                               CONFIG.queue_name)
    client.create_task(parent, {
        'app_engine_http_request': {
            'http_method': 'POST',
            'relative_uri': '/ingestion/all_devices_refresh'}})
    return flask.Response(status=http.HTTPStatus.OK)

  # Task queue executions are POST requests.
  def post(self):
    """Refreshes the ingestion from staging files to live."""
    try:
      IngestAllDevicesJson()
    except filesystem_adapter.FileSystemAdapterException:
      logging.exception('Missing all_devices.json file during refresh.')
      flask.abort(http.HTTPStatus.INTERNAL_SERVER_ERROR,
                  'Missing all_devices.json file during refresh.')

    return flask.Response(response='all_devices.json Ingestion complete.',
                          status=http.HTTPStatus.OK)


def IngestAllDevicesJson():
  """Retrieve the file, parse and save the board to HWID regexp mapping."""

  memcache = memcache_adapter.MemcacheAdapter(namespace='SourceGoldenEye')
  all_devices_json = CONFIG.goldeneye_filesystem.ReadFile('all_devices.json')
  parsed_json = json.loads(all_devices_json)

  regexp_to_device = []

  for device in parsed_json['devices']:
    regexp_to_board = []
    for board in device.get('boards', []):
      regexp_to_board.append((board['hwid_match'], board['public_codename']))
      logging.info('Board: %s', (board['hwid_match'], board['public_codename']))

    if device['hwid_match']:  # only allow non-empty patterns
      regexp_to_device.append((device['hwid_match'], device['public_codename'],
                               regexp_to_board))

      logging.info('Device: %s', (device['hwid_match'],
                                  device['public_codename']))
    else:
      logging.warning('Empty pattern: %s', (device['hwid_match'],
                                            device['public_codename']))

  memcache.Put('regexp_to_device', regexp_to_device)
