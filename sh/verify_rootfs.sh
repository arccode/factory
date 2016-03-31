#!/bin/sh
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script verifies if a chromeos rootfs is valid for activation, by running
# the chromeos-postinst script.

# Deprecated script.
gooftool verify_rootfs "$@"
