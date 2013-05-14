# -*- coding: utf-8 -*-
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This is a wrapper to trun RadiatedCellularGobiImpl into a TestCase."""

import unittest
import factory_common  # pylint: disable=W0611

# pylint: disable=C0301
from cros.factory.test.pytests.radiated_cellular_gobi_impl import RadiatedCellularGobiImpl

class RadiatedCellularGobi(RadiatedCellularGobiImpl, unittest.TestCase):
  def __init__(self, *args, **kwargs):
    super(RadiatedCellularGobi, self ).__init__(*args, **kwargs)
