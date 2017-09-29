# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil

_ENV_DIR = '/var/db/factory/umpire'


def Migrate():
  os.rmdir(os.path.join(_ENV_DIR, 'bin'))
  shutil.copy('session.json', _ENV_DIR)
