# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A yaml module wrapper for HWID v3.

This module overwrites the functions we are interested in to make a separation
from the origin yaml module.
"""

import functools
from yaml import *  # pylint: disable=wildcard-import, unused-wildcard-import


class V3Loader(SafeLoader):
  """A HWID v3 yaml Loader for patch separation."""
  pass


class V3Dumper(SafeDumper):
  """A HWID v3 yaml Dumper for patch separation."""
  pass


# Overwrite the globals from the yaml module
Loader = V3Loader
Dumper = V3Dumper

# Patch functions to use V3Loader and V3Dumper
load = functools.partial(load, Loader=Loader)
load_all = functools.partial(load_all, Loader=Loader)
add_constructor = functools.partial(add_constructor, Loader=Loader)
dump = functools.partial(dump, Dumper=Dumper)
dump_all = functools.partial(dump_all, Dumper=Dumper)
add_representer = functools.partial(add_representer, Dumper=Dumper)
