# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil

_ENV_DIR = '/var/db/factory/umpire'


def Migrate():
  # 0000 is the latest environment version before migration mechanism, and
  # folder 'bin' did exist at the time. As a result, we have to create this
  # folder for consistent, even though it's going to be removed in the next
  # migration. This also save us a try block.
  SUB_DIRS = ('bin', 'conf', 'log', 'resources', 'run', 'temp', 'umpire_data')
  for sub_dir in SUB_DIRS:
    os.mkdir(os.path.join(_ENV_DIR, sub_dir))

  for res_name in (
      'payload.99914b932bd37a50b983c5e7c90ae93b.json',
      'umpire.c3aa51b353868b4a0a353cf513dcc093.yaml'):
    shutil.copy(res_name, os.path.join(_ENV_DIR, 'resources'))

  os.symlink(
      'resources/umpire.c3aa51b353868b4a0a353cf513dcc093.yaml',
      os.path.join(_ENV_DIR, 'active_umpire.yaml'))
