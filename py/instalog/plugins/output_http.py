#!/usr/bin/python2
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Output HTTP plugin.

Sends events to input HTTP plugin.
"""

from __future__ import print_function

import os
import time

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import plugin_base
from instalog.utils.arg_utils import Arg
from instalog.utils import time_utils

from instalog.external import requests


_DEFAULT_BATCH_SIZE = 4096
_DEFAULT_PORT = 8899
_DEFAULT_URL_PATH = ''
_DEFAULT_TIMEOUT = 5
_FAILED_CONNECTION_INTERVAL = 60
_POST_TIMEOUT = 180


class OutputHTTP(plugin_base.OutputPlugin):

  ARGS = [
      Arg('batch_size', int,
          'How many events to queue before transmitting.',
          optional=True, default=_DEFAULT_BATCH_SIZE),
      Arg('timeout', (int, float),
          'Timeout to transmit without full batch.',
          optional=True, default=_DEFAULT_TIMEOUT),
      Arg('hostname', (str, unicode),
          'Hostname of target running input HTTP plugin.',
          optional=False),
      Arg('port', int,
          'Port of target running input HTTP plugin.',
          optional=True, default=_DEFAULT_PORT),
      Arg('url_path', (str, unicode),
          'URL path of target running input HTTP plugin.',
          optional=True, default=_DEFAULT_URL_PATH)
  ]

  def __init__(self, *args, **kwargs):
    """Sets up the plugin."""
    # _max_bytes will be updated after _CheckConnect and _PostRequest.
    self._batch_size = 1
    self._max_bytes = 2 * 1024 * 1024 * 1024  # 2gb
    self._target_url = ''
    super(OutputHTTP, self).__init__(*args, **kwargs)

  def SetUp(self):
    """Sets up the plugin."""
    self._target_url = 'http://%s:%d/%s' % (self.args.hostname,
                                            self.args.port,
                                            self.args.url_path)

  def Main(self):
    """Main thread of the plugin."""
    # Boolean flag to indicate whether or not the target is currently available.
    target_available = False
    last_unavailable_time = float('-inf')
    self._batch_size = self.args.batch_size

    while not self.IsStopping():
      # Should test connect first, and get input HTTP plugin's maximum request.
      if not target_available and not self._CheckConnect():
        if (time_utils.MonotonicTime() >
            (last_unavailable_time + _FAILED_CONNECTION_INTERVAL)):
          last_unavailable_time = time_utils.MonotonicTime()
          self.info('Connection to target unavailable')
        self.Sleep(_FAILED_CONNECTION_INTERVAL)
        continue
      target_available = True

      # We need to know the size of request to avoid too big request, so we
      # cache events in memory before making the connection.
      events = []
      event_stream = self.NewStream()
      if not event_stream:
        self.Sleep(1)
        continue

      for event in event_stream.iter(timeout=self.args.timeout,
                                     count=self._batch_size):
        events.append(event)

      # If no events are available, don't bother sending an empty transmission.
      if not events:
        self.debug('No events available for transmission')
        event_stream.Commit()
        self._batch_size = self.args.batch_size
        continue

      try:
        start_time = time.time()
        request_body = self._PrepareRequestData(events)
        status_code, reason, clen = self._PostRequest(request_body)

        if status_code == 413:  # Request Entity Too Large
          event_stream.Abort()
          if len(events) == 1:
            self.error('One event is bigger than input HTTP plugin\'s maximum '
                       'request limit (event size = %dbytes, input plugin '
                       'maximum size = %dbytes)', clen, self._max_bytes)
            return

          self.info('Request entity too large, and trying to send a half of '
                    'the request')
          # This won't be 0 since it will stop on above when self._batch_size=1.
          self._batch_size /= 2
          continue

        elif status_code != 200:  # Bad Request
          self.error(reason)
          raise Exception

        event_stream.Commit()
        self._batch_size = self.args.batch_size
        elapsed_time = time.time() - start_time

        # Size and speed information.
        total_kbytes = clen / 1024.0
        self.info(
            'Transmitted %d events, total %.2f kB in %.1f sec (%.2f kB/sec)',
            len(events), total_kbytes, elapsed_time,
            total_kbytes / elapsed_time)
      except requests.ConnectionError as e:
        self.warning('Connection failed: Is input HTTP plugin running?')
        self.debug('Connection error: %s', e)
        event_stream.Abort()
        target_available = False
        self.Sleep(1)
      except Exception as e:
        self.exception('Connection or transfer failed: %s', e)
        event_stream.Abort()
        target_available = False
        self.Sleep(1)

  def _PrepareRequestData(self, events):
    """Converts the list of event to requests' format."""
    request_body = []
    att_seq = 0
    for event in events:
      for att_id, att_path in event.attachments.iteritems():
        att_newname = '%s_%03d' % (os.path.basename(att_path), att_seq)
        att_seq += 1
        request_body.append((att_newname, open(att_path, 'rb')))
        event.attachments[att_id] = att_newname
      request_body.append(('event', datatypes.Event.Serialize(event)))
    return request_body

  def _CheckConnect(self):
    """Checks the input HTTP plugin with and empty post request."""
    try:
      resp = requests.get(self._target_url, timeout=2)
      if resp.headers['Maximum-Bytes']:
        self._max_bytes = int(resp.headers['Maximum-Bytes'])
      return resp.status_code == 200
    except requests.exceptions.ConnectionError:
      return False
    except Exception as e:
      self.exception('Unexpected test connect failure: %s', str(e))
      return False

  def _PostRequest(self, data=None):
    """Sends a post request to input HTTP plugin.

    Returns:
      A tuple with (HTTP status code,
                    reason of responded,
                    Content-Length of the request)
    """
    # requests will use about 3 times of data size's memory.
    req = requests.Request(
        'POST',
        url=self._target_url,
        headers={'Multi-Event': 'True'},
        files=data).prepare()
    clen = int(req.headers.get('Content-Length'))
    # Checks the size of request, and doesn't send if bigger than maximum size.
    if clen > self._max_bytes:
      return (413, 'Request Entity Too Large: The request is bigger '
                   'than %d bytes' % self._max_bytes, clen)
    resp = requests.Session().send(req, timeout=_POST_TIMEOUT)
    if resp.headers['Maximum-Bytes']:
      self._max_bytes = int(resp.headers['Maximum-Bytes'])
    return resp.status_code, resp.reason, clen


if __name__ == '__main__':
  plugin_base.main()
