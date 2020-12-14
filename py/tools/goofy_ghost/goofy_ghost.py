#!/usr/bin/env python3
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import subprocess

from cros.factory.test.env import paths
from cros.factory.tools.goofy_ghost import ghost_prop
from cros.factory.utils import argparse_utils
from cros.factory.utils import config_utils
from cros.factory.utils import file_utils
from cros.factory.utils import json_utils


def _WriteGhostProperties():
  properties = config_utils.LoadConfig('goofy_ghost')
  file_utils.TryMakeDirs(
      os.path.dirname(ghost_prop.GOOFY_GHOST_PROPERTIES_FILE))
  json_utils.DumpFile(ghost_prop.GOOFY_GHOST_PROPERTIES_FILE, properties)


@argparse_utils.Command('start')
def _Start(args):
  del args  # Unused.

  _WriteGhostProperties()
  cmd = [
      'ghost', '--fork', '--prop-file', ghost_prop.GOOFY_GHOST_PROPERTIES_FILE
  ]
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
