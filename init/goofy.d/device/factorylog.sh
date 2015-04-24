#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(hungte) Probe and create Frecon TTY if possible.
TTY=/dev/tty3

if [ -c "${TTY}" ]; then
  tail -n 48 -F /var/factory/log/factory.log >>/dev/tty3 &
fi
