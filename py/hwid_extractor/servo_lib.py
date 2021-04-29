# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(chungsheng): b/180554195, remove this workaround after splitting
# chromite.

from typing import List, NamedTuple


class FirmwareConfig(NamedTuple):
  """Stores dut controls for specific servos.

  Attributes:
    dut_control_on:  2d array formatted like [["cmd1", "arg1", "arg2"],
                                              ["cmd2", "arg3", "arg4"]]
                       with commands that need to be ran before flashing,
                       where cmd1 will be run before cmd2.
    dut_control_off: 2d array formatted like [["cmd1", "arg1", "arg2"],
                                              ["cmd2", "arg3", "arg4"]]
                       with commands that need to be ran after flashing,
                       where cmd1 will be run before cmd2.
    programmer:      programmer argument (-p) for flashrom and futility.
  """
  dut_control_on: List[List[str]]
  dut_control_off: List[List[str]]
  programmer: str
