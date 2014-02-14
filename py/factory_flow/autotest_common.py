#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A helper module to set up sys.path so that autotest_lib.* can be located."""

# pylint: disable=F0401

import os
import sys

CROS_WORKON_SRCROOT = os.environ['CROS_WORKON_SRCROOT']
autotest_dir = os.path.join(
    CROS_WORKON_SRCROOT, 'src', 'third_party', 'autotest', 'files')
sys.path.insert(0, os.path.join(autotest_dir, 'client'))
import setup_modules
sys.path.pop(0)
setup_modules.setup(base_path=autotest_dir, root_module_name='autotest_lib')
