#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import os
import subprocess

import factory_common  # pylint: disable=unused-import
from cros.factory.test.env import paths
from cros.factory.test.test_lists import manager
from cros.factory.tools.goofy_ghost import ghost_prop
from cros.factory.utils import argparse_utils
from cros.factory.utils import config_utils
from cros.factory.utils import file_utils


def _WriteGhostProperties():
  properties = config_utils.LoadConfig('goofy_ghost')
  properties['active_test_list'] = manager.Manager.GetActiveTestListId()
  file_utils.TryMakeDirs(
      os.path.dirname(ghost_prop.GOOFY_GHOST_PROPERTIES_FILE))
  file_utils.WriteFile(ghost_prop.GOOFY_GHOST_PROPERTIES_FILE,
                       json.dumps(properties))


@argparse_utils.Command('start')
def _Start(args):
  del args  # Unused.

  _WriteGhostProperties()
  cmd = [
      'ghost', '--fork', '--prop-file', ghost_prop.GOOFY_GHOST_PROPERTIES_FILE
  ]
  # TODO(pihsun): Have a way to specify --tls-no-verify.
  pem_file = os.path.join(paths.DATA_DIR, 'overlord.pem')
  if os.path.exists(pem_file):
    cmd.extend(['--tls-cert-file', pem_file])
  subprocess.check_call(cmd)


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
