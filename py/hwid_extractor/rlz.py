# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import os


RLZ_JSON = os.path.join(os.path.dirname(__file__), 'rlz.json')


class RLZData:
  """RLZ data stores the mapping from rlz codes to name of reference boards."""

  def __init__(self):
    self._rlz_data = {}
    if os.path.isfile(RLZ_JSON):
      with open(RLZ_JSON, 'r') as f:
        self._rlz_data = json.load(f)

  def Get(self, *args, **kargs):
    return self._rlz_data.get(*args, **kargs)

  @staticmethod
  def _ParseAllDevicesJSON(all_device):
    res = {}
    for device in all_device.get('devices', []):
      cr50_board_id = device.get('cr50_board_id')
      if not cr50_board_id or cr50_board_id == 'ZZCR':
        # "ZZCR" is a generic brandcode that all devices use in early bring-up
        # until the permanent brandcode is created.
        continue
      reference_board = device.get('reference_board')
      if not reference_board:
        continue
      res[cr50_board_id] = reference_board['public_codename']
    return res

  def UpdateFromAllDevicesJSON(self, all_device):
    """Update rlz.json with all_device.json.

    all_devices.json: gs://chromeos-build-release-console/all_devices.json

    Ask user to upload all_device.json, parse it and store the results to
    rlz.json.

    Args:
      all_device: The parsed json object of all_devices.json.
    Returns:
      True if update successfully.
    """
    rlz_data = self._ParseAllDevicesJSON(all_device)
    if not rlz_data:
      return False
    with open(RLZ_JSON, 'w') as f:
      json.dump(rlz_data, f)
    self._rlz_data = rlz_data
    return True
