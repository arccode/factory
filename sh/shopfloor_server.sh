#!/bin/bash
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Wrapper to run shopfloor server.
# This must be in the same directory as the factory.par file or
# a directory named 'cros'.
set -e

dir=$(dirname $(readlink -f $0))
if [ -d $dir/cros ]; then
  lib=$dir
elif [ -e $dir/factory.par ]; then
  lib=$dir/factory.par
else
  echo Unable to find factory archive file $dir/factory.par >&2
  exit 1
fi

exec env PYTHONPATH=$lib:$PYTHONPATH python \
    $CROS_SHOPFLOOR_PYTHON_OPTS \
    -m cros.factory.shopfloor.shopfloor_server "$@"
