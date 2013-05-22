#!/usr/bin/python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
Directory lister is a ls-like wrapper to return listed files in yaml format.
The output of this tool will be a dictionary where key is file name and value
is the file size.

  ./list_dir.py <directory>
"""
import os
import sys
import yaml

if __name__ == '__main__':
  if len(sys.argv[1:]) != 1:
    raise ValueError('Accept only single argument as directory name')
  dir_path = sys.argv[1]

  files = dict()
  for file_path in os.listdir(dir_path):
    full_path = os.path.join(dir_path, file_path)
    if not os.path.isfile(full_path):
      continue
    files[file_path] = os.path.getsize(full_path)
  print yaml.safe_dump(files, canonical=True)
