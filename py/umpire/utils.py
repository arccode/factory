# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Umpire utility classes."""


import factory_common  # pylint: disable=W0611
from cros.factory.common import AttrDict, Singleton


class Registry(AttrDict):
  """Registry is a singleton class that inherits from AttrDict.

  Example:
    config_file = Registry().get('active_config_file', None)
    Registry().extend({
      'abc': 123,
      'def': 456
    })
    assertEqual(Registry().abc, 123)
  """
  __metaclass__ = Singleton
