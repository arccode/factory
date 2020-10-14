#!/usr/bin/env python3
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input HTTP Testlog plugin.

Receives events from HTTP requests.
Can easily send one Testlog format event by curl:
$ curl -i -X POST \
       --form-string 'event={Testlog JSON}' TARGET_HOSTNAME:TARGET_PORT
$ curl -i -X POST \
       --form-string '{
                "status": "PASSED",
                "stationInstallationId": "92228272-056e-4329-a432-64d3ed6dfa0c",
                "uuid": "8b127476-2604-422a-b9b1-f05e4f14bf72",
                "stationDeviceId": "e7d3227e-f12d-42b3-9c64-0d9e8fa02f6d",
                "type": "station.test_run",
                "testName": "webcam_test",
                "apiVersion": "0.1",
                "testRunId": "8b127472-4593-4be8-9e94-79f228fc1adc",
                "startTime": {
                    "__type__": "datetime",
                    "value": "2017-01-05T13:01:45.489000Z"},
                "time": {
                    "__type__": "datetime",
                    "value": "2017-01-05T13:01:45.503000Z"},
                "testType": "vswr",
                "seq": 8202191,
                "attachments": {
                    "front_camera.png": {
                        "description": "Image captured by the front camera.",
                        "path": "/var/factory/log/attachments/front_camera.png",
                        "mimeType": "image/png"
                    }
                }
           }' \
       --form 'front_camera.png=@/path/to/front_camera.png' \
       TARGET_HOSTNAME:TARGET_PORT

Also can send multiple events by adding header through curl:
$ curl -i -X POST \
       --form-string 'event={Testlog JSON}' \
       --form-string 'event=[{Testlog JSON}, {Attachments}]' \
       --form-string 'event=[{Testlog JSON}, {"0": "att_0"}]' \
       --form 'att_0=@/path/to/attachment_name' \
       -H 'Multi-Event: True' \
       TARGET_HOSTNAME:TARGET_PORT
(See datatypes.py Event.Deserialize for details of event format.)
"""

import logging
import time

from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import input_http
from cros.factory.instalog.plugins import testlog_common
from cros.factory.instalog.testlog import testlog
from cros.factory.instalog.utils import arg_utils
from cros.factory.instalog.utils.arg_utils import Arg
from cros.factory.instalog.utils import log_utils


class InputHTTPTestlog(input_http.InputHTTP):

  ARGS = arg_utils.MergeArgs(
      input_http.InputHTTP.ARGS,
      [
          Arg('log_level_threshold', (str, int, float),
              'The logLevel threshold for all message events.',
              default=logging.NOTSET)
      ]
  )

  def __init__(self, *args, **kwargs):
    super(InputHTTPTestlog, self).__init__(*args, **kwargs)

    self.noisy_info = log_utils.NoisyLogger(
        self.info, suppress_timeout=3600,
        suppress_logger=lambda message, *args, **kargs: None,
        all_suppress_logger=lambda message, *args, **kargs: None)

    if isinstance(self.args.log_level_threshold, (int, float)):
      self.threshold = self.args.log_level_threshold
    else:
      self.threshold = getattr(logging, self.args.log_level_threshold)

  def _CheckFormat(self, event, client_node_id):
    """Checks the event is following the Testlog format and sets attachments.

    Raises:
      Exception: the event is not conform to the Testlog format.
    """
    if 'attachments' in event:
      if len(event.attachments) != len(event['attachments']):
        raise ValueError("event['attachment'] are not consistent with "
                         'attachments in requests.')
      for key in event['attachments']:
        if key not in event.attachments:
          raise ValueError("event['attachment'] are not consistent with "
                           'attachments in requests.')
    elif event.attachments:
      raise ValueError("event['attachment'] are not consistent with "
                       'attachments in requests.')

    if event['apiVersion'] != testlog.TESTLOG_API_VERSION:
      self.noisy_info.Log('Received old format(%s) events from "%s"',
                          event['apiVersion'], client_node_id)
    # UpgradeEvent and FromDict will raise exception when the event is invalid.
    event = testlog_common.UpgradeEvent(event)
    testlog.EventBase.FromDict(event.payload)
    event['__testlog__'] = True

    if (event['type'] == 'station.message' and
        getattr(logging, event.get('logLevel', 'CRITICAL')) < self.threshold):
      return False

    # The time on the DUT is not reliable, so we are going to use the time on
    # the factory server.
    event['time'] = time.time()

    return True


if __name__ == '__main__':
  plugin_base.main()
