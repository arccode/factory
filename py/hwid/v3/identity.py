# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Identity class for the HWID v3 framework."""

import collections


Identity = collections.namedtuple('Identity', [
    'project',  # A string of the name of the Chromebook project.
    'binary_string',  # A "01" string of the HWID binary string.
    'encoded_string'  # A string of the encoded HWID string,
                      # which prefix should be the project name.
])
