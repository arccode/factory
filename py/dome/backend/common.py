# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

# TODO(youcheng): Move some constants into this file.

PROJECT_NAME_RE = r'[-_0-9a-zA-Z]+'

def IsDomeDevServer():
  return 'DOME_DEV_SERVER' in os.environ
