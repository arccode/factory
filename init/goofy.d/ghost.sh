#!/bin/sh
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FACTORY_DIR="/usr/local/factory"

export PATH="${FACTORY_DIR}/bin:${FACTORY_DIR}/bin/overlord:${PATH}"
"${FACTORY_DIR}"/bin/goofy_ghost start >/dev/null 2>&1
