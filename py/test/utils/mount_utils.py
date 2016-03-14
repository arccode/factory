#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Mount utilities."""

import factory_common  # pylint: disable=W0611
from contextlib import contextmanager


@contextmanager
def Mount(dut, source, target, options=None, types=None):
  """Mount source to target

  Mount source to target, and umount it when exists.

  Args:
    dut: dut objects to run the mount command with.
    source: source path.
    target: target path.
    options: options for mount, which is used with mount -o <options>.
    types: types of the source, which is used with mount -t <types>.
  """

  cmd = ['toybox', 'mount']
  if types:
    cmd += ['-t', types]
  if options:
    cmd += ['-o', options]
  cmd += [source, target]

  dut.CheckCall(cmd)
  try:
    yield
  finally:
    dut.CheckCall(['toybox', 'umount', target])
