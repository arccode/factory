#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Input testlog file plugin.

Subclasses InputLogFile to correctly parse a testlog.json file.
"""

from __future__ import print_function

import json

import instalog_common  # pylint: disable=W0611
from instalog import datatypes
from instalog import plugin_base
from instalog.plugins import input_log_file


class InputTestlogFile(input_log_file.InputLogFile):

  def ParseLine(self, line):
    """Parses the given line into an Instalog Event object."""
    data = json.loads(line)
    # TODO(kitching): Create a testlog schema file and check against the JSON
    #                 for validity.
    attachments = {}
    # TODO(kitching): Ask itspeter how the path to an attachment should be
    #                 determined.  If it's not contained within the JSON, we
    #                 need to add another ARG called attachment_dir.
    if 'attachments' in data:
      for att_id, att_data in data['attachments'].iteritems():
        attachments[att_id] = att_data['path']
    return datatypes.Event(data)


if __name__ == '__main__':
  plugin_base.main()
