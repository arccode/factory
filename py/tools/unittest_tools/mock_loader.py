#!/usr/bin/env python3
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import os
import sys
import shutil
import tempfile


_PY_DIR_PATH = os.path.abspath(os.path.join(__file__, '..', '..', '..'))


class Loader:

  def __init__(self):
    self._tmp_dir_path = ''

  def __enter__(self):
    self._tmp_dir_path = tempfile.mkdtemp()
    fake_path = os.path.join(self._tmp_dir_path, 'cros', 'factory')
    real_path = os.path.join(self._tmp_dir_path, 'real', 'cros', 'factory')

    self._SetupFactoryDir(src_path=_PY_DIR_PATH, dst_path=fake_path,
                          enable_mocking=True)
    self._SetupFactoryDir(src_path=_PY_DIR_PATH, dst_path=real_path,
                          enable_mocking=False)

    # Update sys.path by filtering the current factory import path out and
    # insert our fake instead
    sys.path = [p for p in sys.path if 'factory' not in p]
    sys.path.insert(0, self._tmp_dir_path)
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    """Remove the directory created by tempfile.mkdtemp()"""
    shutil.rmtree(self._tmp_dir_path)

  def _SymlinkFile(self, src, dst):
    """Symlink a file from source to destination."""
    if not os.path.exists(src):
      raise FileNotFoundError(f'{src} not found')
    dir_path = os.path.dirname(dst)
    if not os.path.exists(dir_path):
      os.makedirs(dir_path)
    os.symlink(src, dst)

  def _SetupFactoryDir(self, src_path, dst_path, enable_mocking):
    """Create a directory for module importing.

    Args:
    enable_mocking: Determine whether we copy the mocked files
                    instead the real files.
    """
    files = glob.glob(os.path.join(src_path, '**/*.*'), recursive=True)
    file_set = set(files)
    for src_file in files:
      if src_file.endswith('_mocked.py'):
        continue
      dst_file = src_file.replace(src_path, dst_path)
      src_file_name, _ = os.path.splitext(src_file)
      mocked_file = src_file_name + '_mocked.py'
      if enable_mocking and mocked_file in file_set:
        self._SymlinkFile(mocked_file, dst_file)
      else:
        self._SymlinkFile(src_file, dst_file)
