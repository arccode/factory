# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog service upgrade the buffer plugin.

See https://chromium-review.googlesource.com/989530 for more details.
"""

import os
import shutil


_OLD_BUFFER_DIR = '/var/db/factory/umpire/umpire_data/instalog/data/buffer'


def Migrate():
  if os.path.isdir(_OLD_BUFFER_DIR):
    for i in range(4):
      for j in range(4):
        if i == 0 and j == 0:
          continue
        new_buffer_dir = os.path.join(_OLD_BUFFER_DIR, '%d_%d' % (i, j))
        if not os.path.exists(new_buffer_dir):
          os.mkdir(new_buffer_dir)
        sample_consumers_file = os.path.join(
            _OLD_BUFFER_DIR, '0_0', 'consumers.json')
        target_consumers_file = os.path.join(new_buffer_dir, 'consumers.json')
        shutil.copyfile(sample_consumers_file, target_consumers_file)
