#!/usr/bin/env python3
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Output HTTP plugin.

Sends events to input HTTP plugin.
"""

import logging
import os
import time

import requests

from cros.factory.instalog import datatypes
from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import http_common
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import file_utils
from cros.factory.instalog.utils import time_utils

from cros.factory.instalog.external import gnupg


_DEFAULT_BATCH_SIZE = 1024
_DEFAULT_URL_PATH = ''
_DEFAULT_TIMEOUT = 5
_FAILED_CONNECTION_INTERVAL = 60


class OutputHTTP(plugin_base.OutputPlugin):

  ARGS = [
      Arg('batch_size', int,
          'How many events to queue before transmitting.',
          default=_DEFAULT_BATCH_SIZE),
      Arg('timeout', (int, float),
          'Timeout to transmit without full batch.',
          default=_DEFAULT_TIMEOUT),
      Arg('hostname', str,
          'Hostname of target running input HTTP plugin.'),
      Arg('port', int,
          'Port of target running input HTTP plugin.',
          default=http_common.DEFAULT_PORT),
      Arg('url_path', str,
          'URL path of target running input HTTP plugin.',
          default=_DEFAULT_URL_PATH),
      Arg('enable_gnupg', bool,
          'Enable to use GnuPG.',
          default=False),
      Arg('gnupg_home', str,
          'The home directory of GnuPG.',
          default=None),
      Arg('target_key', str,
          'The fingerprint of target GnuPG public key in this machine.',
          default=None)
  ]

  def __init__(self, *args, **kwargs):
    """Sets up the plugin."""
    # _max_bytes will be updated after _CheckConnect and _PostRequest.
    self._batch_size = 1
    self._max_bytes = http_common.DEFAULT_MAX_BYTES
    self._target_url = ''
    self._gpg = None
    super(OutputHTTP, self).__init__(*args, **kwargs)

  def SetUp(self):
    """Sets up the plugin."""
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('gnupg').setLevel(logging.WARNING)
    if self.args.enable_gnupg:
      self.info('Enable GnuPG to encrypt and sign the data')
      http_common.CheckGnuPG()
      self._gpg = gnupg.GPG(gnupghome=self.args.gnupg_home)
      self.info('GnuPG home directory: %s', self._gpg.gnupghome)
      if not self.args.target_key:
        raise ValueError('Missing target GnuPG public key')

      self._EncryptData('Checks the target public key is valid.')
      self.info('Finished checking the target public key')

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
        # Create the temporary directory for attachments.
        with file_utils.TempDirectory(prefix='output_http_') as tmp_dir:
          self.debug('Temporary directory for attachments: %s', tmp_dir)

          start_time = time.time()
          request_body = self._PrepareRequestData(events, tmp_dir)
          status_code, reason, clen = self._PostRequest(request_body)

          if status_code == 413:  # Request Entity Too Large
            event_stream.Abort()
            if len(events) == 1:
              self.error('One event is bigger than input HTTP plugin\'s '
                         'maximum request limit (event size = %dbytes, input '
                         'plugin maximum size = %dbytes)',
                         clen, self._max_bytes)
              return

            self.info('Request entity too large, and trying to send a half of '
                      'the request')
            # This won't be 0 since it will stop on above when
            # self._batch_size=1.
            self._batch_size //= 2
            continue

          if status_code != 200:  # Bad Request
            self.error(reason)
            raise Exception

          event_stream.Commit()
          self._batch_size = self.args.batch_size
          elapsed_time = time.time() - start_time

          # Size and speed information.
          total_kbytes = clen / 1024
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

  def _PrepareRequestData(self, events, tmp_dir):
    """Converts the list of event to requests' format."""
    request_body = []
    att_seq = 0
    for event in events:
      for att_id, att_path in event.attachments.items():
        att_newname = '%s_%03d' % (os.path.basename(att_path), att_seq)
        att_seq += 1
        if self._gpg:
          att_path = self._EncryptFile(att_path, tmp_dir)
        request_body.append((att_newname, open(att_path, 'rb')))
        event.attachments[att_id] = att_newname
      serialized_event = datatypes.Event.Serialize(event)
      if self._gpg:
        serialized_event = self._EncryptData(serialized_event)
      request_body.append(('event', serialized_event))
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
        headers={'Multi-Event': 'True',
                 'Node-ID': str(self.GetNodeID())},
        files=data).prepare()
    clen = int(req.headers.get('Content-Length'))
    # Checks the size of request, and doesn't send if bigger than maximum size.
    if clen > self._max_bytes:
      return (413, 'Request Entity Too Large: The request is bigger '
                   'than %d bytes' % self._max_bytes, clen)
    resp = requests.Session().send(req, timeout=http_common.HTTP_TIMEOUT)
    if resp.headers['Maximum-Bytes']:
      self._max_bytes = int(resp.headers['Maximum-Bytes'])
    return resp.status_code, resp.reason, clen

  def _EncryptData(self, data):
    """Encrypts and signs the data by target key and default secret key."""
    if isinstance(data, str):
      data = data.encode('utf-8')
    encrypted_data = self._gpg.encrypt(
        data,
        self.args.target_key,
        sign=self._gpg.list_keys(True)[0]['fingerprint'],
        always_trust=False)
    if not encrypted_data.ok:
      raise Exception('Failed to encrypt data! Log: %s' % encrypted_data.stderr)
    return encrypted_data.data

  def _EncryptFile(self, file_path, target_dir):
    """Encrypts and signs the file by target key and default secret key."""
    encrypt_path = file_utils.CreateTemporaryFile(prefix='encrypt_',
                                                  dir=target_dir)
    with open(file_path, 'rb') as plaintext_file:
      encrypted_data = self._gpg.encrypt_file(
          plaintext_file,
          self.args.target_key,
          sign=self._gpg.list_keys(True)[0]['fingerprint'],
          output=encrypt_path,
          always_trust=False)
      if not encrypted_data.ok:
        raise Exception(
            'Failed to encrypt file! Log: %s' % encrypted_data.stderr)
    return encrypt_path


if __name__ == '__main__':
  plugin_base.main()
