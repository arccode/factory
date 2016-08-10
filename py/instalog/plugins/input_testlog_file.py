#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input testlog file plugin.

Subclasses InputLogFile to correctly parse a testlog.json file.
"""

from __future__ import print_function

import datetime
import json
import os

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import plugin_base
from instalog.plugins import input_log_file


class InputTestlogFile(input_log_file.InputLogFile):

  def ParseLine(self, path, line):
    """Parses a line and returns an Instalog Event object."""
    del path  # We don't use the path of the log file.
    data = json.loads(line)
    data['__testlog__'] = True
    if 'time' in data:
      data['time'] = datetime.datetime.strptime(
          data['time'], '%Y-%m-%dT%H:%M:%S.%fZ')
    if 'startTime' in data:
      data['startTime'] = datetime.datetime.strptime(
          data['startTime'], '%Y-%m-%dT%H:%M:%S.%fZ')
    if 'endTime' in data:
      data['endTime'] = datetime.datetime.strptime(
          data['endTime'], '%Y-%m-%dT%H:%M:%S.%fZ')
    # TODO(kitching): Figure out the proper way to validate the event:
    #                 (a) Use a JSON schema.
    #                 (b) Import testlog and use FromJSON directly.
    attachments = {}
    if 'attachments' in data:
      for att_id, att_data in data['attachments'].iteritems():
        # Only add the attachment if the path exists.
        if os.path.isfile(att_data['path']):
          attachments[att_id] = att_data['path']
        else:
          self.warning('Testlog attachment not found on disk, '
                       'silently dropping: %r', att_data)
    return datatypes.Event(data, attachments)


if __name__ == '__main__':
  plugin_base.main()
