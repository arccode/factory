# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common utility functions that are not touch specific.

The SimpleSystem() and SimpleSystemOutput() functions are grabbed from
hardware_Trackpad and were written by truty@.

Note that in order to be able to use this module on a system without the
factory stuffs, e.g., on a Beagle Bone, this module does not depend on
any factory modules on purpose.
"""

from __future__ import print_function

import logging
import subprocess

from subprocess import PIPE, STDOUT


def SimpleSystem(cmd):
  """Execute a system command."""
  ret = subprocess.call(cmd, shell=True)
  if ret:
    logging.warning('Command (%s) failed (ret=%s).', cmd, ret)
  return ret


def SimpleSystemOutput(cmd):
  """Execute a system command and get its output."""
  try:
    proc = subprocess.Popen(cmd, shell=True, stdout=PIPE, stderr=STDOUT)
    stdout, _ = proc.communicate()
  except Exception, e:
    logging.warning('Command (%s) failed (%s).', cmd, e)
  else:
    return None if proc.returncode else stdout.strip()

