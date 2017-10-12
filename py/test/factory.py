# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common types and routines for factory test infrastructure.

This library provides common types and routines for the factory test
infrastructure. This library explicitly does not import gtk, to
allow its use by the autotest control process.
"""

from __future__ import print_function

import factory_common  # pylint: disable=unused-import
from cros.factory.test import session


# TODO(hungte) Remove this when everyone is using new location session.console.
console = session.console


class FactoryTestFailure(Exception):
  """Failure of a factory test."""
