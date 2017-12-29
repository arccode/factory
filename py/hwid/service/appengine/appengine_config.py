# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""AppEngine Config which runs before App starting up."""

import logging
import os

# pylint: disable=import-error, no-name-in-module
from google.appengine.ext import vendor


def _SetEnviron():
  root_dir = os.path.dirname(os.path.realpath(__file__))
  os.environ.setdefault('CROS_REGIONS_DATABASE',
                        os.path.join(root_dir, 'cros-regions.json'))
  os.environ.setdefault('CROS_FACTORY_PY_ROOT', root_dir)
  logging.debug('os.environ=%s', str(os.environ))


try:
  vendor.add('lib')
except ValueError:
  logging.info('Cannot find lib/')

_SetEnviron()
