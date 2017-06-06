#!/bin/sh
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
CONFIG_PATH="static/miniomaha.conf"
set -e
cd "$(dirname $(readlink -f "$0"))"
if [ ! -e "${CONFIG_PATH}" ]; then
  ./make_factory_package.sh \
    --board "$(cat .default_board)" \
    --test_image ../test_image/* \
    --release_image ../release_image/* \
    --toolkit ../toolkit/* \
    --hwid ../hwid/* \
    --firmware ../firmware/* \
    --complete_script ../complete/*
fi
echo "Validating configuration..."
python miniomaha.py --validate_factory_config
echo "Starting download server."
python miniomaha.py
