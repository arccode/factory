#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from django.core.management import execute_manager

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.frontend import settings


if __name__ == "__main__":
  execute_manager(settings)
