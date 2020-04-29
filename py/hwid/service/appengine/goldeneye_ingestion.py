# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handler that ingests the latest all_devices.json from GoldenEye."""

import logging
import json

# pylint: disable=import-error, no-name-in-module
from google.appengine.api import taskqueue
import webapp2  # pylint: disable=import-error

from cros.factory.hwid.service.appengine.config import CONFIG
from cros.factory.hwid.service.appengine import filesystem_adapter
from cros.factory.hwid.service.appengine import memcache_adapter


MEMCACHE_NAMESPACE = 'SourceGoldenEye'


class AllDevicesRefreshHandler(webapp2.RequestHandler):
  """Handle update of a possibly new all_devices.json file."""

  # pylint: disable=useless-super-delegation
  def __init__(self, request, response):
    super(AllDevicesRefreshHandler, self).__init__(request, response)

  # Cron jobs are always GET requests, we are not actually doing the work
  # here just queuing a task to be run in the background.
  def get(self):
    taskqueue.add(url='/ingestion/all_devices_refresh')

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
