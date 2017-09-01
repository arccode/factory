#!/bin/sh
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Clear all factory test states when the internal storage has been changed.
# Note we can't call 'factory clear' because goofy (providing goofy_rpc) is not
# available at the moment.
echo "Device ID change detected, resetting all test results..."
rm -f /var/factory/state/tests
