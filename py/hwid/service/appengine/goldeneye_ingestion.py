# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handler that ingests the latest all_devices.json from GoldenEye."""

import json
import logging

# TODO(clarkchung): Remove google.appengine package dependency
# pylint: disable=no-name-in-module, import-error
from google.appengine.api.app_identity import app_identity
# pylint: enable=no-name-in-module, import-error
from google.cloud import tasks
import webapp2  # pylint: disable=import-error

from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import memcache_adapter
from cros.factory.hwid.v3 import filesystem_adapter


MEMCACHE_NAMESPACE = 'SourceGoldenEye'


class AllDevicesRefreshHandler(webapp2.RequestHandler):
  """Handle update of a possibly new all_devices.json file."""

  # pylint: disable=useless-super-delegation
  def __init__(self, request, response):
    super(AllDevicesRefreshHandler, self).__init__(request, response)

  # Cron jobs are always GET requests, we are not actually doing the work
  # here just queuing a task to be run in the background.
  def get(self):
    client = tasks.CloudTasksClient()
    # TODO(clarkchung): Change `app_identity.get_application_id()` to
    # os.environ.get('GOOGLE_CLOUD_PROJECT') in py3 runtime
    parent = client.queue_path(app_identity.get_application_id(),
                               CONFIG.project_region, 'default')
    client.create_task(parent, {
        'app_engine_http_request': {
            'http_method': 'POST',
            'relative_uri': '/ingestion/all_devices_refresh'}})

  # Task queue executions are POST requests.
  def post(self):
    """Refreshes the ingestion from staging files to live."""
    try:
      IngestAllDevicesJson()
    except filesystem_adapter.FileSystemAdapterException as e:
      logging.error('Missing all_devices.json file during refresh.')
      logging.error(e)
      self.abort(500, 'Missing all_devices.json file during refresh.')

    self.response.write('all_devices.json Ingestion complete.')


def IngestAllDevicesJson():
  """Retrieve the file, parse and save the board to HWID regexp mapping."""

  memcache = memcache_adapter.MemcacheAdapter(namespace='SourceGoldenEye')
  all_devices_json = CONFIG.goldeneye_filesystem.ReadFile('/all_devices.json')
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
