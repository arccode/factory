#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Ensure the misc/sshkeys files have right file permission 600.

FACTORY_DIR="$(readlink -f "$(dirname "$(readlink -f "$0")")/../..")"

if [ -d "${FACTORY_DIR}/misc/sshkeys" ]; then
  chmod 600 "${FACTORY_DIR}/misc/sshkeys/testing_rsa"
fi
