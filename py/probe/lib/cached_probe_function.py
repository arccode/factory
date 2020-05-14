# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import glob
import logging
import os

from cros.factory.probe import function
from cros.factory.probe.lib import probe_function
from cros.factory.utils.arg_utils import Arg


class InvalidCategoryError(Exception):
  pass


class CachedProbeFunction(probe_function.ProbeFunction):
  """An abstract class of probe function which caches the probe data forever.

  The cached probed results is recorded as a dictionary which categories probed
  results together.  This class supplies two different use cases.  The simple
  one is just to output the probed results of all devices.  Or the caller can
  also specify the category of the target devices so that the output will only
  contain the probed results of the corresponding devices.
  """
  DUMMY_CATEGORY = 'dummy_category'

  _CACHED_DEVICES = None

  def Probe(self):
    self._InitCachedData()

    try:
      category = self.GetCategoryFromArgs()
    except InvalidCategoryError as e:
      logging.error(str(e))
      return function.NOTHING

    if not category:
      return sum(self._CACHED_DEVICES.values(), [])
    return self._CACHED_DEVICES.get(category, function.NOTHING)

  @classmethod
  def CleanCachedData(cls):
    """Cleans the cached data, this method is mainly for unittesting."""
    cls._CACHED_DEVICES = None

  def GetCategoryFromArgs(self):
    """Gets the category of the target devices from the function arguments.

    Returns:
      The category name or `None` if the caller doesn't specify any category.

    Raises:
      `InvalidCategoryError` if the caller uses this function mistakenly.
    """
    raise NotImplementedError

  @classmethod
  def ProbeAllDevices(cls):
    """Probe the system to get all probed results of all devices.

    Returns:
      A list of probed results of all devices if this function is always
          supposed to be called without specifying an category; a dict
          which maps the category name to a list of probed results.
    """
    raise NotImplementedError

  @classmethod
  def _InitCachedData(cls):
    if cls._CACHED_DEVICES is None:
      probed_data = cls.ProbeAllDevices()
      if probed_data is None:
        probed_data = {}
      elif isinstance(probed_data, list):
        probed_data = {cls.DUMMY_CATEGORY: probed_data}
      cls._CACHED_DEVICES = {k: v if isinstance(v, list) else [v]
                             for k, v in probed_data.items()}


class LazyCachedProbeFunction(probe_function.ProbeFunction):
  """An abstract probe function which probes and caches the data only in need.

  This class is similar to `CachedProbeFunction` but this class strickly forces
  all probed results being classified into categories and the method
  `GetCategoryfromArgs` implemented by the sub-class must return an category,
  `None` is not acceptable.  In `CachedProbeFunction`, the cached data will
  be filled once the function is called, but in this class, the cached data
  of each category is initialized individually.
  """
  _CACHED_DEVICES = None

  def Probe(self):
    try:
      category = self.GetCategoryFromArgs()
    except InvalidCategoryError as e:
      logging.error(str(e))
      return function.NOTHING

    return self._GetCachedProbedData(category)

  @classmethod
  def CleanCachedData(cls):
    """Cleans the cached data, this method is mainly for unittesting."""
    cls._CACHED_DEVICES = None

  def GetCategoryFromArgs(self):
    """Gets the category of the target devices from the function arguments.

    Returns:
      The category name.

    Raises:
      `InvalidCategoryError` if the caller uses this function mistakenly.
    """
    raise NotImplementedError

  @classmethod
  def ProbeDevices(cls, category):
    """Probe the devices of a specific category.

    Args:
      category: The category name.

    Returns:
      A list of dict of probe results.
    """
    raise NotImplementedError

  @classmethod
  def _GetCachedProbedData(cls, category):
    if cls._CACHED_DEVICES is None:
      cls._CACHED_DEVICES = {}

    if category not in cls._CACHED_DEVICES:
      try:
        probed_results = cls.ProbeDevices(category)
      except Exception as e:
        logging.error('Failed to probe the category %r: %r', category, e)
        probed_results = function.NOTHING

      cls._CACHED_DEVICES[category] = probed_results

    return cls._CACHED_DEVICES[category]


class GlobPathCachedProbeFunction(CachedProbeFunction):
  """Glob a specific path to get all devices.

  In many cases, devices are all presented as sub-directories in the same sysfs
  directory so to probe all devices we can simply go through every
  sub-directories in a specific directory.  This class implements the procedure
  of globbing the paths so that the sub-class only needs to care about probing
  a single device.
  """

  ARGS = [
      Arg('dir_path', str, 'The path used to search for device sysfs data. '
          'First all symlinks are resolved, to the the "real" path. Then '
          'iteratively search toward parent folder until the remaining path '
          'contains the relevent data fields.', default=None),
  ]

  GLOB_PATH = None

  @classmethod
  def ProbeDevice(cls, dir_path):
    """Probe a single device located in the specific directory.

    Args:
      dir_path: The path of the directory entry of the device.

    Returns:
      None if the given `dir_path` is invalid; otherwise returns a dict of
          probed data.
    """
    raise NotImplementedError

  def GetCategoryFromArgs(self):
    return (os.path.abspath(os.path.realpath(self.args.dir_path))
            if self.args.dir_path is not None else None)

  @classmethod
  def ProbeAllDevices(cls):
    ret = {}

    for globbed_path in glob.glob(cls.GLOB_PATH):
      abs_path = os.path.abspath(os.path.realpath(globbed_path))
      if abs_path in ret:
        continue

      try:
        probed_result = cls.ProbeDevice(globbed_path)
      except Exception as e:
        logging.error('Failed to probe the device at %r: %r', globbed_path, e)
        probed_result = None

      if probed_result:
        probed_result['device_path'] = globbed_path
        ret[abs_path] = probed_result

    return ret
