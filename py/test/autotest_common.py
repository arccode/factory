#!/usr/bin/python
#
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A helper module to set up sys.path so that autotest_lib.client.* can be
located."""

from __future__ import print_function

# pylint: disable=F0401

import os
import sys

import factory_common   # pylint:disable=W0611
from cros.factory.test import utils

if utils.in_cros_device():
  autotest_dir = '/usr/local/autotest'
else:
  CROS_WORKON_SRCROOT = os.environ['CROS_WORKON_SRCROOT']
  autotest_dir = os.path.join(
      CROS_WORKON_SRCROOT, 'src', 'third_party', 'autotest', 'files', 'client')

# Temporarily remove the factory cros module, which causes autotest to get
# confused when assigning autotest_lib.client.cros.
_cros = sys.modules.get('cros')
if _cros:
  del sys.modules['cros']

sys.path.insert(0, autotest_dir)
import setup_modules
sys.path.pop(0)
setup_modules.setup(base_path=autotest_dir,
    root_module_name='autotest_lib.client')

# Re-add the factory cros module.
if _cros:
  sys.modules['cros'] = _cros
