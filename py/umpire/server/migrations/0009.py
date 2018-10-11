# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import os

_ENV_DIR = '/var/db/factory/umpire'


def Migrate():
  parameters_dir = os.path.join(_ENV_DIR, 'parameters')
  os.mkdir(parameters_dir)
  with open(os.path.join(parameters_dir, 'parameters.json'), 'w') as f:
    f.write(json.dumps({'files': [], 'dirs': []}))
