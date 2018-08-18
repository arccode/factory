# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os


PORT = 4013

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
STATIC_DIR = os.path.realpath(
    os.path.join(SCRIPT_DIR, '..', 'frontend', 'dist'))
PRIVATE_FACTORY_RELPATH = os.path.join(
    'chromeos-base', 'factory-board', 'files')
