# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os

SCRIPT_PATH = os.path.realpath(__file__)
FACTORY_PATH = os.path.dirname(os.path.dirname(SCRIPT_PATH))
PLATFORM_PATH = os.path.dirname(FACTORY_PATH)
