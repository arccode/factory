# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A system module providing access to permanet storage on DUT"""

import posixpath

from cros.factory.device import device_types


class Path(device_types.DeviceComponent):
  """Provies operations on pathnames, similar to os.path.

  If the operation doesn't need to access DUT, e.g. join and split,
  we just use the posixpath module. These functions are listed in
  Path.DELEGATED_ATTRIBUTES.
  Not all functions in posixpath are ported, unsupported methods:

      getmtime, getatime, getctime, ismount, walk, expanduser,
      expandvars, abspath, samefile, sameopenfile, samestat, relpath
  """

  DELEGATED_ATTRIBUTES = [
      'normcase', 'isabs', 'join', 'splitdrive', 'split', 'splitext',
      'basename', 'dirname', 'commonprefix', 'normpath', 'curdir', 'pardir',
      'extsep', 'sep', 'pathsep', 'defpath', 'altsep', 'devnull',
      'supports_unicode_filenames'
  ]

  def __getattr__(self, attr):
    if attr in Path.DELEGATED_ATTRIBUTES:
      return getattr(posixpath, attr)
    type_name = type(self).__name__
    if attr in posixpath.__all__:
      raise NotImplementedError('%r is not implemented in %r' % (attr,
                                                                 type_name))
    raise AttributeError('%r has no attribute %r' % (type_name, attr))

  def exists(self, path):
    """Tests whether a path exists. Returns False for broken symbolic links."""
    return self._device.Call(['test', '-e', path]) == 0

  def getsize(self, path):
    if not self.exists(path):
      raise OSError('No such file or directory: %r' % path)

    cmd = ['stat', '--printf', '%F\n%s', path]
    output = self._device.CheckOutput(cmd)
    (file_type, size) = output.splitlines()

    if file_type in ('block special file', 'block device'):
      return int(self._device.CallOutput(['blockdev', '--getsize64', path]))
    # For other files, just returns what we got from stat
    return int(size)

  def isdir(self, path):
    """Returns True if path refers to an existing directory."""
    return self._device.Call(['test', '-d', path]) == 0

  def isfile(self, path):
    """Returns True if path refers to a regular file."""
    return self._device.Call(['test', '-f', path]) == 0

  def islink(self, path):
    """Returns True if path refers to a symbolic link."""
    return self._device.Call(['test', '-h', path]) == 0

  def lexists(self, path):
    """Tests whether a path exists. Returns True for broken symbolic links."""
    return self.islink(path) or self.exists(path)

  def realpath(self, path):
    """Returns a canonical path of given pathname.

    Symbolic links are resolved if possible.

    Example:
      Consider the content of tmp directory looks like:
        tmp
        `-- a
            `-- b
                `-- c -> ../

        >>> print self.realpath('/path/to/tmp/a/b/c/d/e')
        /path/to/tmp/a/d/e
    """

    # this should never failed, a path should always be returned
    output = self._device.CallOutput(['realpath', '-m', path])
    return output.splitlines()[0]


class AndroidPath(Path):
  """Provides operations on pathnames for Android systems."""

  def realpath(self, path):
    """Returns a canonical path of given pathname."""

    # The realpath command on Android device does not have '-m' options,
    # which means all but the last component must exist.
    # We implement this function by calling 'realpath' to resolve each
    # component.
    # If we can't resolve any of component, we will stop and append rest of
    # components to current path, and normalize the path.
    #
    # For example:
    #   If we are going to resolve /path/to/some/file,
    #   we will do the following things:
    #     $ realpath /
    #     /
    #     $ realpath /path
    #     /path
    #     $ realpath /path/to     # /path/to is a symbolic link to /other/path
    #     /other/path
    #     $ realpath /other/path/some
    #     /other/path/some
    #     $ realpath /other/path/some/file
    #     /other/path/some/file
    #  And the final result is '/other/path/some/file'

    # Since in many cases, the 'path' actually exists, we can reduce average
    # cost by checking the entire path first.
    output = self._device.CallOutput(['realpath', path])
    if output:
      return output.strip()

    if self.isabs(path):
      bits = ['/'] + path.split('/')[1:]
    else:
      bits = ['./'] + path.split('/')

    # This should never fail (we are asking realpath for '/' or './').
    output = self._device.CheckOutput(['realpath', bits[0]])
    current = output.strip()

    # Try to append each subdirectory to current path.
    for i in range(1, len(bits)):
      if bits[i] == '.' or not bits[i]:  # /./ or //
        continue

      if bits[i] == '..':
        current = self.dirname(current)
        continue

      output = self._device.CallOutput(
          ['realpath', self.join(current, bits[i])])
      if not output:
        # We can't find realpath of 'current/bits[i]',
        # it might be a symbolic loop or non-existing file,
        # so we just append everything left and normalize the path.
        return self.normpath(self.join(current, *bits[i:]))
      current = output.strip()
    return current
