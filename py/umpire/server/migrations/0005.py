# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json


def Migrate():
  with open('/var/db/factory/umpire/active_umpire.json') as f:
    config = json.load(f)
  if 'ip' in config or 'port' in config:
    raise RuntimeError(
        'Who on earth would configure "ip" or "port" in Umpire config?')
