# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A factory test to verify MLB board version."""

from __future__ import print_function

import re
import unittest

import factory_common   # pylint: disable=W0611
from cros.factory import system
from cros.factory.test import args
from cros.factory.test import phase


class MLBVersionTest(unittest.TestCase):
  """A factory test to verify MLB board version."""

  ARGS = [
      args.Arg(
          'expected_version', (str, unicode),
          ('The expected version string. If not given, try to match the board '
           'version with current build phase'),
          optional=True),
  ]

  def runTest(self):
    board_version = system.GetBoard().GetBoardVersion()
    if self.args.expected_version:
      self.assertEquals(
          self.args.expected_version, board_version,
          ('Board version mismatch. Expect to see board version %s, but the '
           'actual board version is %s') %
          (self.args.expected_version, board_version))
    else:
      current_phase = phase.GetPhase()
      if current_phase in [phase.PVT, phase.PVT_DOGFOOD]:
        expected_version_prefix = '(PVT|MP)'
      else:
        expected_version_prefix = str(current_phase)

      self.assertTrue(
          re.search(r'^%s' % expected_version_prefix, board_version.upper()),
          ('In phase %s, expect board version to start with %s, '
           'but got board version %s') %
          (current_phase, expected_version_prefix, board_version))
