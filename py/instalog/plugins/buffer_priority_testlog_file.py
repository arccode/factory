#!/usr/bin/env python3
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Priority multi-file-based testlog buffer."""

from cros.factory.instalog import plugin_base
from cros.factory.instalog.plugins import buffer_priority_file


class BufferPriorityFile(buffer_priority_file.BufferPriorityFile):

  def EventLevel(self, event):
    if event.get('type') == 'station.test_run':
      return 0
    if event.get('type') != 'station.message':
      return 1
    if event.get('logLevel') != 'INFO':
      return 2
    return 3


if __name__ == '__main__':
  plugin_base.main()
