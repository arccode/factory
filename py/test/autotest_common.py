# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''
Prepares autotest-compatible namespace for ChromeOS factory framework.
'''

from __future__ import print_function

import os
import sys

# Temporarily remove the factory cros module, which causes autotest to get
# confused when assigning autotest_lib.client.cros.
if 'cros' in sys.modules:
  del sys.modules['cros']

# Choose the correct location of the autotest source tree.
src_root = os.environ.get('CROS_WORKON_SRCROOT')
if src_root:
  # chroot: autotest files will be in Chromium source tree.
  autotest_bin_dir = os.path.join(src_root,
      'src/third_party/autotest/files/client/bin')
else:
  # Test image: autotest files will be in /usr/local.
  autotest_bin_dir = '/usr/local/autotest/bin'
assert os.path.isdir(autotest_bin_dir), 'No autotest tree available'

# Load 'common' module from autotest/bin namespace.
sys.path.insert(0, autotest_bin_dir)
import common  # pylint: disable=W0611
sys.path.pop(0)
