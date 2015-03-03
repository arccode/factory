#!/bin/sh
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Customize Chrome startup settings.
mount --bind "$(dirname $0)/chrome_dev.conf" /etc/chrome_dev.conf

# For factory environment, we don't need to preserve Chrome session data.
mount -t tmpfs none /home/chronos
