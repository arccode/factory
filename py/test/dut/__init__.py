#!/usr/bin/env python
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import factory_common  # pylint: disable=W0611

from cros.factory.test.dut.links import utils as link_utils


def Create(**kargs):
  """Creates a DUT instance by given options.

  Currently this simply creates a DUT link object. In future this should be
  replaced by a Board instance.
  """
  return link_utils.Create(**kargs)
