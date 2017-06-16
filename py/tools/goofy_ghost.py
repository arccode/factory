#!/usr/bin/python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import os
import subprocess

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test.test_lists import test_lists
from cros.factory.utils import argparse_utils
from cros.factory.utils import config_utils
from cros.factory.utils import file_utils


GOOFY_GHOST_PROPERTIES_FILE = os.path.join(paths.RUNTIME_VARIABLE_DATA_DIR,
                                           'goofy_ghost.json')


def _WriteGhostProperties():
  # TODO(pihsun): Complete JSON schema for ghost properties.
  properties = config_utils.LoadConfig('goofy_ghost')
  properties['active_test_list'] = test_lists.GetActiveTestListId()
  file_utils.WriteFile(GOOFY_GHOST_PROPERTIES_FILE, json.dumps(properties))


@argparse_utils.Command('start')
def _Start(args):
  del args  # Unused.

  _WriteGhostProperties()
  subprocess.check_call(
      ['ghost', '--fork', '--prop-file', GOOFY_GHOST_PROPERTIES_FILE])


@argparse_utils.Command('reset')
def _Reset(args):
  del args  # Unused.

  _WriteGhostProperties()
  subprocess.check_call(['ghost', '--reset'])


def main():
  args = argparse_utils.ParseCmdline('Ghost runner for Goofy.')
  args.command(args)


if __name__ == '__main__':
  main()
