# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''
Prepares autotest-compatible namespace for ChromeOS factory framework.
'''

import os, sys

# Load 'common' module from autotest/bin folder, for 'autotest_bin' namespace.
sys.path.insert(0, os.path.realpath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'bin')))
import common
sys.path.pop(0)
