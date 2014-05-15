# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A module for running a given command on the host."""

import shlex

import factory_common   # pylint: disable=W0611
from cros.factory.factory_flow.common import FactoryFlowCommand, board_cmd_arg
from cros.factory.hacked_argparse import CmdArg
from cros.factory.utils import process_utils


class RunHostCommandError(Exception):
  """Run host command error."""
  pass


class RunHostCommand(FactoryFlowCommand):
  """Runs the given command on the host."""
  args = [
      board_cmd_arg,
      CmdArg('--cmd', required=True, help='the command to run'),
  ]

  def Run(self):
    process_utils.Spawn(shlex.split(self.options.cmd),
                        log=True, check_call=True)
