#!/bin/sh
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Derived from dev_debug_vboot.
#
# This script checks if system firmware and SSD images are ready for verified
# booting.
#

# Deprecated script.
gooftool verify_keys "$@"
