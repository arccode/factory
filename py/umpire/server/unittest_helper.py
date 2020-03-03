# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Collections of helpers for unittests in this package."""

import os
import sys


def ExecScriptWithTrial():
  """Execute the current script with `trial` plusing additional arguments."""
  cmd_args = ('trial', '--temp-directory=/tmp/_trial_temp', sys.argv[0])
  os.execvp(cmd_args[0], cmd_args)
