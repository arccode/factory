# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Methods to manipulate ghost properties file."""

import json
import os

from cros.factory.test.env import paths
from cros.factory.utils import process_utils


DEVICE_GOOFY_GHOST_PROPERTIES_FILE = os.path.join(paths.DATA_DIR, 'config',
                                                  'goofy_ghost.json')
GOOFY_GHOST_PROPERTIES_FILE = os.path.join(paths.RUNTIME_VARIABLE_DATA_DIR,
                                           'factory', 'goofy_ghost.json')
GOOFY_GHOST_BIN = os.path.join(paths.FACTORY_DIR, 'bin', 'goofy_ghost')


def ReadProperties():
  with open(GOOFY_GHOST_PROPERTIES_FILE, 'r') as fin:
    return json.load(fin)


def UpdateDeviceProperties(update):
  properties = {}
  if os.path.exists(DEVICE_GOOFY_GHOST_PROPERTIES_FILE):
    with open(DEVICE_GOOFY_GHOST_PROPERTIES_FILE, 'r') as fin:
      properties = json.load(fin)
  properties.update(update)
  with open(DEVICE_GOOFY_GHOST_PROPERTIES_FILE, 'w') as fout:
    json.dump(properties, fout, indent=2)

  process_utils.Spawn([GOOFY_GHOST_BIN, 'reset'], check_call=True, log=True)
