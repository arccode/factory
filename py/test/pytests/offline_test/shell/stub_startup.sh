#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# A stub script for init/startup

# init/startup will run scripts under init/main.d if $1 == 'main',
# let's mimic this behavior.
# The "$1" = "" case is for DUT test image using the old /etc/init version,
# which calls init/startup only once, without any argument.
if [ "$1" = "main" -o "$1" = "" ]; then
  "/usr/local/factory/init/main.d/offline-test.sh"
fi
