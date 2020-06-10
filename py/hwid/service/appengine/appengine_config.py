# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""AppEngine Config which runs before App starting up."""

import logging
import os
import pkg_resources

# pylint: disable=import-error, no-name-in-module
from google.appengine.ext import vendor


def _SetEnviron():
  root_dir = os.path.dirname(os.path.realpath(__file__))
  os.environ.setdefault('CROS_REGIONS_DATABASE',
                        os.path.join(root_dir, 'cros-regions.json'))
  os.environ.setdefault('CROS_FACTORY_PY_ROOT', root_dir)
  logging.debug('os.environ=%s', str(os.environ))


# Filtering logs from the AppEngine dashbaord is very easy. Logs everything
# here.
logging.getLogger().setLevel(logging.DEBUG)

try:
  vendor.add('lib')
except ValueError:
  logging.info('Cannot find lib/')
pkg_resources.working_set.add_entry('lib')

try:
  vendor.add('protobuf_out')
except ValueError:
  logging.info('Cannot find protobuf_out/')

_SetEnviron()
