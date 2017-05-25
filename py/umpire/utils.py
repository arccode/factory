# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire utility classes."""

import logging
import yaml

from twisted.internet import defer

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import common
from cros.factory.utils import file_utils
from cros.factory.utils import type_utils


class Registry(type_utils.AttrDict):
  """Registry is a singleton class that inherits from AttrDict.

  Example:
    config_file = Registry().get('active_config_file', None)
    Registry().extend({
      'abc': 123,
      'def': 456
    })
    assertEqual(Registry().abc, 123)
  """
  __metaclass__ = type_utils.Singleton


def ConcentrateDeferreds(deferred_list):
  """Collects results from list of deferreds.

  Returns a deferred object that fires error callback on first error.
  And the original failure won't propagate back to original deferred object's
  next error callback.

  Args:
    deferred_list: Iterable of deferred objects.

  Returns:
    Deferred object that fires error on any deferred_list's errback been
    called. Its callback will be trigged when all callback results are
    collected. The gathered result is a list of deferred object callback
    results.
  """
  return defer.gatherResults(deferred_list, consumeErrors=True)


def Deprecate(method):
  """Logs error of calling deprecated function.

  Args:
    method: the deprecated function.
  """
  def _Wrapper(*args, **kwargs):
    logging.error('%s is deprecated', method.__name__)
    return method(*args, **kwargs)

  _Wrapper.__name__ = method.__name__
  return _Wrapper


# pylint: disable=R0901
class BundleManifestIgnoreGlobLoader(yaml.Loader):
  """A YAML loader that loads factory bundle manifest with !glob ignored."""

  def __init__(self, *args, **kwargs):
    def FakeGlobConstruct(loader, node):
      del loader, node  # Unused.
      return None

    yaml.Loader.__init__(self, *args, **kwargs)
    self.add_constructor('!glob', FakeGlobConstruct)


# pylint: disable=R0901
class BundleManifestLoader(yaml.Loader):
  """A YAML loader that loads factory bundle manifest with !glob ignored."""

  def __init__(self, *args, **kwargs):
    yaml.Loader.__init__(self, *args, **kwargs)
    # TODO(deanliao): refactor out Glob from py/tools/finalize_bundle.py
    #     to py/utils/bundle_manifest.py and move the LoadBundleManifest
    #     related methods to that module.
    self.add_constructor('!glob', file_utils.Glob.Construct)


def LoadBundleManifest(path, ignore_glob=False):
  """Loads factory bundle's MANIFEST.yaml (with !glob ignored).

  Args:
    path: path to factory bundle's MANIFEST.yaml
    ignore_glob: True to ignore glob.

  Returns:
    A Python object the manifest file represents.

  Raises:
    IOError if file not found.
    UmpireError if the manifest fail to load and parse.
  """
  file_utils.CheckPath(path, description='factory bundle manifest')
  try:
    loader = (BundleManifestIgnoreGlobLoader if ignore_glob else
              BundleManifestLoader)
    with open(path) as f:
      return yaml.load(f, Loader=loader)
  except Exception as e:
    raise common.UmpireError('Failed to load MANIFEST.yaml: ' + str(e))
