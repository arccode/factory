#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os


"""Filename of the generated test script."""
SCRIPT_FILE_NAME = 'test.sh'

"""Name of the subdirectory in factory directories to store our resource."""
DIRNAME = 'shell_offline_test'

"""Path to resource of shell offline test."""
CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))

OFFLINE_JOB_NAME = 'offline-test'


def ScriptRoot(dut):
  """Path to script directory for offline test."""
  return dut.path.join(dut.storage.GetFactoryRoot(), DIRNAME)


def TestScriptPath(dut):
  """Path to generated test script."""
  return dut.path.join(ScriptRoot(dut), SCRIPT_FILE_NAME)


def DataRoot(dut):
  """Path to store data for offline test."""
  return dut.path.join(dut.storage.GetDataRoot(), DIRNAME)


class OfflineTestError(Exception):
  pass
