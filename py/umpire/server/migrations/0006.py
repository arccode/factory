# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog service upgrade the buffer plugin.

See https://chromium-review.googlesource.com/989530 for more details.
"""

import os


_OLD_BUFFER_DIR = '/var/db/factory/umpire/umpire_data/instalog/data/buffer'
_NEW_BUFFER_DIR = os.path.join(_OLD_BUFFER_DIR, '0_0')


def Migrate():
  if os.path.isdir(_OLD_BUFFER_DIR):
    if not os.path.exists(_NEW_BUFFER_DIR):
      os.mkdir(_NEW_BUFFER_DIR)
    for file_name in os.listdir(_OLD_BUFFER_DIR):
      if (file_name.startswith('consumer') or
          file_name in ['data.json', 'metadata.json', 'attachments']):
        os.rename(os.path.join(_OLD_BUFFER_DIR, file_name),
                  os.path.join(_NEW_BUFFER_DIR, file_name))
