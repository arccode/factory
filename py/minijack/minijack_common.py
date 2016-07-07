# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import sys


MINIJACK_DIR = os.path.dirname(
    os.path.realpath(__file__.replace('.pyc', '.py')))
MINIJACK_PARENT_DIR = os.path.realpath(os.path.join(MINIJACK_DIR, '..'))
MINIJACK_EXTERNAL_DIR = os.path.realpath(os.path.join(MINIJACK_DIR, 'external'))

sys.path.insert(0, MINIJACK_PARENT_DIR)
sys.path.insert(0, MINIJACK_EXTERNAL_DIR)
