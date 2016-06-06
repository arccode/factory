# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire bundle wrapper

We don't take advantage of django's database functionality because this system
should ideally be stateless. In other words, all information should be kept in
umpire instead of the database. This may not be possible for now, since umpire
config still lacks some critical information such as the history record.

TODO(littlecvr): make umpire config complete such that it contains all the
                 information we need.
"""

class Bundle(object):
  """Provide functions to manipulate bundles in umpire."""

  def __init__(self, name):
    pass

  @staticmethod
  def ListAll():
    """Return all bundles as a list."""
    raise NotImplementedError

  @staticmethod
  def UploadNew():
    """Upload a new bundle."""
    raise NotImplementedError
