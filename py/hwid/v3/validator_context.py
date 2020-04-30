# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Validator context for HWID DB.

The class ValidatorContext holds required information to use in validation
process.  Note that this class is added in a standalone file to prevent circular
import.
"""


import collections


ValidatorContext = collections.namedtuple('ValidatorContext',
                                          ['filesystem_adapter'])
