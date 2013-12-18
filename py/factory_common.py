#!/usr/bin/python
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A helper module to set up sys.path so that cros.factory.* can be located."""

import os, sys
sys.path.append(
    os.path.join(
        os.path.dirname(os.path.dirname(
                os.path.realpath(__file__.replace('.pyc', '.py')))),
        'py_pkg'))
