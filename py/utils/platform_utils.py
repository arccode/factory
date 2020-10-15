# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Platform-specific utilities."""

import os
import platform
import time


# Cache to speed up.
_CURRENT_PLATFORM_SYSTEM = platform.system()

# Constants for platform.system(). Note the 'Default' is locally defined for
# internal usage.
_SYSTEM_WINDOWS = 'Windows'
_SYSTEM_LINUX = 'Linux'
_SYSTEM_DEFAULT = 'Default'


# Conditional imports. For syntax checking and cross-compiling, we want to
# ignore conditional import errors.
try:
  # pylint: disable=wrong-import-order,wrong-import-position
  if _CURRENT_PLATFORM_SYSTEM == _SYSTEM_WINDOWS:
    pass
  else:
    import fcntl
except ImportError:
  pass


# A dictionary to hold declarations from @Provider.
_PROVIDER_MAP = {}


def Provider(api_name, systems):
  """Decorator to provide an API on given platform systems.

  args:
    api_name: A string for API name.
    systems: A list of supported platform systems.
  """
  assert not isinstance(systems, str), "systems must be list."
  if api_name not in _PROVIDER_MAP:
    _PROVIDER_MAP[api_name] = {}
  def ProviderDecorator(func):
    _PROVIDER_MAP[api_name].update({name: func for name in systems})
    return func
  return ProviderDecorator


def GetProvider(api_name, system=None):
  """Finds right provider for given system by API name.

  Args:
    api_name: A string for API name.
    system: A string for system name, as defined in platform.system().

  Returns:
    The function that implements target API on given system.

  Raises:
    NotImplementedError if the given system has no implementation for API.
  """
  systems = _PROVIDER_MAP.get(api_name, {})
  if system is None:
    system = _CURRENT_PLATFORM_SYSTEM
  func = systems.get(system, systems.get(_SYSTEM_DEFAULT, None))
  if func is None:
    raise NotImplementedError('No implementation on %s for <%s>' %
                              (system, api_name))
  return func


@Provider('MonotonicTime', [_SYSTEM_WINDOWS])
def WindowsMonotonicTime():
  # TODO(kitching): Write a MonotonicTime for Windows.  See notes written here:
  # https://docs.python.org/3/library/time.html#time.monotonic
  # Fall back to time.time on Windows systems.
  return time.time()


_clock_gettime = None


@Provider('MonotonicTime', [_SYSTEM_DEFAULT])
def UnixMonotonicTime():
  """Gets the raw monotonic time.

  This function opens librt.so with ctypes and call:

    int clock_gettime(clockid_t clk_id, struct timespec *tp);

  to get raw monotonic time.

  Returns:
    The system monotonic time in seconds.
  """
  CLOCK_MONOTONIC_RAW = 4
  global _clock_gettime  # pylint: disable=global-statement

  if _clock_gettime:
    return _clock_gettime()

  # ctypes and ctypes.utils may be not availalbe, especially on Android which
  # does not have librt so we have to do delay-loading here.
  try:
    import ctypes
    import ctypes.util

    class TimeSpec(ctypes.Structure):
      """A representation of struct timespec in C."""
      _fields_ = [
          ('tv_sec', ctypes.c_long),
          ('tv_nsec', ctypes.c_long),
      ]

    librt_name = ctypes.util.find_library('rt')
    librt = ctypes.cdll.LoadLibrary(librt_name)
    clock_gettime = librt.clock_gettime
    clock_gettime.argtypes = [ctypes.c_int, ctypes.POINTER(TimeSpec)]
    t = TimeSpec()

    def rt_clock_gettime():
      if clock_gettime(CLOCK_MONOTONIC_RAW, ctypes.pointer(t)) != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
      return t.tv_sec + 1e-9 * t.tv_nsec

    _clock_gettime = rt_clock_gettime

  except Exception:
    # Either ctypes or librt failed. Try to provide system time if possible.
    _clock_gettime = time.time

  return _clock_gettime()


@Provider('FileLock', [_SYSTEM_DEFAULT])
def UnixFileLock(fd, do_lock=True, is_exclusive=True, is_blocking=True):
  if do_lock:
    fcntl.flock(fd, ((fcntl.LOCK_EX if is_exclusive else fcntl.LOCK_SH) |
                     (0 if is_blocking else fcntl.LOCK_NB)))
  else:
    fcntl.flock(fd, fcntl.LOCK_UN)


# pylint: disable=unused-argument
@Provider('FileLock', [_SYSTEM_WINDOWS])
def WindowsFileLock(fd, do_lock=True, is_exclusive=True, is_blocking=True):
  # TODO(hungte) Implement file locking on Windows.
  pass
