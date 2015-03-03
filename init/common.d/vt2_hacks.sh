#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(hungte) Only apply the customizations on Chromium OS environment.

# Install console (VT2) customizations
mount --bind "$(dirname $(readlink -f $0))/vt2_hacks/cursor.sh" \
  /etc/profile.d/cursor.sh
