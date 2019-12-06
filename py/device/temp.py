# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A system module providing access of temprary files on remote DUT."""

from contextlib import contextmanager

from cros.factory.device import device_types


class TemporaryFiles(device_types.DeviceComponent):
  """Provides access to temporary files and directories on DUT-based systems.

  Examples:

   temp_dir = self.dut.temp.mktemp(True, '.ext', 'mytmp')

   with self.dut.temp.TempFile() as tmp_path:
     self.dut.Call('echo test > %s' % tmp_path)

   with self.dut.temp.TempDirectory() as tmp_dir:
     self.dut.Call('gen_output -C %s' % tmp_dir)

  """

  # pylint: disable=redefined-builtin
  def mktemp(self, is_dir, suffix='', prefix='cftmp', dir=None):
    """Creates a temporary file or directory on DUT."""
    template = '%s.XXXXXX%s' % (prefix, suffix)
    # http://unix.stackexchange.com/questions/30091/
    # GNU mktemp takes TEMPLATE with 6X as full path unless DIR is not assigned.
    # BSD mktemp takes arbitary X with -t (deprecated by GNU) for DIR. DIR can
    # be only set by env TMPDIR.
    # Android mktemp always assumes TEMPLATE does not include DIR.
    # toybox  mktemp works like Android but TEMPLATE is also limited to 6 char.
    # mktemp.org also has a different working style.
    # The implementation below is for GNU mktemp.
    args = ['mktemp']
    if is_dir:
      args += ['-d']
    args += ['--tmpdir' if dir is None else '--tmpdir=%s' % dir]
    args += [template]
    return self._device.CheckOutput(args).strip()

  @contextmanager
  def TempFile(self, **kargs):
    """Yields an unopened temporary file.

    The file is not opened, and it is deleted when the context manager
    is closed if it still exists at that moment.

    Args:
      Any allowable arguments to tempfile.mktemp (e.g., prefix,
        suffix, dir).
    """
    path = self.mktemp(False, **kargs)
    try:
      yield path
    finally:
      self._device.Call(['rm', '-f', path])


  @contextmanager
  def TempDirectory(self, **kargs):
    """Yields a temporary directory.

    The temp directory is deleted when the context manager is closed if it still
    exists at that moment.

    Args:
      Any allowable arguments to tempfile.mkdtemp (e.g., prefix,
        suffix, dir).
    """
    path = self.mktemp(True, **kargs)
    try:
      yield path
    finally:
      self._device.Call(['rm', '-rf', path])


class AndroidTemporaryFiles(TemporaryFiles):
  """Access to temporary objects on Android systems."""

  # pylint: disable=redefined-builtin
  def mktemp(self, is_dir, suffix='', prefix='cftmp', dir=None):
    """Creates a temporary file or directory on DUT."""

    template = '%s.XXXXXX%s' % (prefix, suffix)
    args = ['mktemp']
    if dir is not None:
      args += ['-p', dir]
    if is_dir:
      args += ['-d']
    args += [template]
    return self._device.CheckOutput(args).strip()


class DummyTemporaryFiles(TemporaryFiles):
  DUMMY_FILE_NAME = 'DUMMY_TEMP_FILE'

  # pylint: disable=redefined-builtin
  def mktemp(self, is_dir, suffix='', prefix='cftmp', dir=None):
    return self.DUMMY_FILE_NAME

  @contextmanager
  def TempFile(self, **kargs):
    path = self.mktemp(False, **kargs)
    try:
      yield path
    finally:
      pass

  @contextmanager
  def TempDirectory(self, **kargs):
    path = self.mktemp(True, **kargs)
    try:
      yield path
    finally:
      pass
