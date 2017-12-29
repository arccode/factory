# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handler for ingestion."""

import cgi
import logging

# pylint: disable=import-error, no-name-in-module
from google.appengine.api import taskqueue
import webapp2
import yaml

import factory_common  # pylint: disable=unused-import
from cros.factory.hwid.service.appengine import config
from cros.factory.hwid.service.appengine import filesystem_adapter


class DevUploadHandler(webapp2.RequestHandler):

  def __init__(self, request, response):  # pylint: disable=super-on-old-class
    super(DevUploadHandler, self).__init__(request, response)
    self._hwid_filesystem = config.hwid_filesystem

  def post(self):
    """Uploads a file to the cloud storage of the server."""
    if 'data' not in self.request.POST or 'path' not in self.request.POST:
      logging.warn('Required fields missing on request: %r', self.request.POST)
      self.abort(400)

    data = self.request.POST['data']
    path = self.request.get('path')

    logging.debug('Got upload request: %r', self.request.POST)

    if not isinstance(data, cgi.FieldStorage):
      logging.warn('Got request without file in data field.')
      self.abort(400)

    self._hwid_filesystem.WriteFile(path, data.file.read())

    for filename in self._hwid_filesystem.ListFiles():
      self.response.write('%s\n' % filename)


class RefreshHandler(webapp2.RequestHandler):
  """Handle update of possibley new yaml files.

  In normal circumstances the cron job triggers the refresh hourly, however it
  can be triggered by admins.  The actual work is done by the default
  background task queue.

  The task queue POSTS back into this hander to do the
  actual work.

  Refresing the data regularly take just over the 60 second timeout for
  interactive requests.  Using a task process extends this deadline to 10
  minutes which should be more than enough headroom for the next few years.
  """

  def __init__(self, request, response):  # pylint: disable=super-on-old-class
    super(RefreshHandler, self).__init__(request, response)
    self.hwid_filesystem = config.hwid_filesystem
    self.hwid_manager = config.hwid_manager

  # Cron jobs are always GET requests, we are not acutally doing the work
  # here just queuing a task to be run in the background.
  def get(self):
    taskqueue.add(url='/ingestion/refresh')

  # Task queue executions are POST requests.
  def post(self):
    """Refreshes the ingestion from staging files to live."""

    # TODO(yllin): Reduce memory footprint.
    # Get board.yaml
    try:
      metadata_yaml = self.hwid_filesystem.ReadFile('/staging/boards.yaml')

      # parse it
      metadata = yaml.safe_load(metadata_yaml)

      self.hwid_manager.UpdateBoards(metadata)

    except filesystem_adapter.FileSystemAdaptorException:
      logging.error('Missing file during refresh.')
      self.abort(500, 'Missing file during refresh.')

    self.hwid_manager.ReloadMemcacheCacheFromFiles()
    self.response.write('Ingestion complete.')
