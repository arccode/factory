# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.utils import json_utils
from cros.factory.utils import type_utils


STATUS = type_utils.Enum(['Waiting', 'Updating', 'Success', 'Failure'])


class StatusUpdater:

  def __init__(self, status_path):
    self.status_path = status_path
    self.status_dict = {}

  def SetStatus(self, url, status, update_timestamp=None):
    timestamp = ''
    if update_timestamp:
      timestamp = update_timestamp
    elif url in self.status_dict:
      timestamp = self.status_dict[url]['update_timestamp']

    self.status_dict[url] = {
        'status': status,
        'update_timestamp': timestamp
    }
    json_utils.DumpFile(self.status_path, self.status_dict)
