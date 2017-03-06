# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire utility classes."""

import logging
import os
import shutil
from twisted.internet import defer
import urllib
import yaml

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils
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


def VerifyResource(res_file):
  """Verifies a resource file.

  Verifies a file by calculating its md5sum and checking if its leading
  N-digits are the same as filename's hash section.

  Args:
    res_file: path to a resource file

  Returns:
    True if the file's checksum is verified.
  """
  if not os.path.isfile(res_file):
    logging.error('VerifyResource: file missing: %s', res_file)
    return False
  hashsum = GetHashFromResourceName(res_file)
  if not hashsum:
    logging.error('Ill-formed resource filename: %s', res_file)
    return False
  calculated_hashsum = file_utils.MD5InHex(res_file)
  return calculated_hashsum.startswith(hashsum)


def ParseResourceName(res_file):
  """Parses resource file name.

  Args:
    res_file: path to a resource file

  Returns:
    (base_name, version, hash).
    None if res_file is ill-formed.
  """
  match = common.RESOURCE_FILE_PATTERN.match(res_file)
  return match.groups() if match else None


def GetHashFromResourceName(res_file):
  """Gets hash from resource file name.

  Args:
    res_file: path to a resource file

  Returns:
    hash value in resource file name's tail.
    None if res_file is ill-formed.
  """
  match = common.RESOURCE_FILE_PATTERN.match(res_file)
  return match.group(3) if match else None


def GetVersionFromResourceName(res_file):
  """Gets version from resource file name.

  Args:
    res_file: path to a resource file

  Returns:
    Version in resource file name's second latest segment (# delimited).
    None if res_file is ill-formed.
  """
  match = common.RESOURCE_FILE_PATTERN.match(res_file)
  return match.group(2) if match else None


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


def UnpackFactoryToolkit(env, toolkit_resource):
  """Unpacks factory toolkit in resources to toolkits/hash directory.

  Note that if the destination directory already exists, it doesn't unpack.

  Args:
    env: UmpireEnv object.
    toolkit_resource: Path to factory toolkit resources.

  Returns:
    Unpacked directory. None if toolkit_resource is invalid.
  """
  if not isinstance(toolkit_resource, str) or not toolkit_resource:
    logging.error('Invalid toolkit_resource %r', toolkit_resource)
    return None

  toolkit_path = env.GetResourcePath(toolkit_resource)
  toolkit_hash = GetHashFromResourceName(toolkit_resource)
  unpack_dir = os.path.join(env.device_toolkits_dir, toolkit_hash)
  if os.path.isdir(unpack_dir):
    logging.info('UnpackFactoryToolkit destination dir already exists: %s',
                 unpack_dir)
    return unpack_dir

  # Extract to temp directory first then move the directory to prevent
  # keeping a broken toolkit.
  with file_utils.TempDirectory() as temp_dir:
    process_utils.Spawn([toolkit_path, '--noexec', '--target', temp_dir],
                        check_call=True, log=True)

    # Create toolkit directory's base directory first.
    unpack_dir_base = os.path.split(unpack_dir)[0]
    file_utils.TryMakeDirs(unpack_dir_base)

    # Use shutil.move() instead of os.rename(). os.rename calls OS
    # rename() function. And under Linux-like OSes, this system call
    # creates and removes hardlink, that only works when source path and
    # destination path are both on same filesystem.
    shutil.move(temp_dir, unpack_dir)
    logging.debug('Factory toolkit extracted to %s', unpack_dir)

  # Inject MD5SUM in extracted toolkit as umpire read only.
  md5sum_path = os.path.join(unpack_dir, 'usr', 'local', 'factory', 'MD5SUM')
  with open(md5sum_path, 'w') as f:
    f.write('%s\n' % file_utils.MD5InHex(toolkit_path))
  logging.debug('%r generated', md5sum_path)

  return unpack_dir


def ComposeDownloadConfig(download_files):
  """Composes download config.

  Based on given download_files, composes config file for netboot install.

  Args:
    download_files: list of resource files (full path) to include in the
        download config.

  Returns:
    Download config (multi-line string).
  """
  def GetChannel(base_name):
    """Converts file base name to download channel."""
    if base_name == 'rootfs-release':
      return 'RELEASE'
    elif base_name == 'rootfs-test':
      return 'FACTORY'
    else:
      return base_name.upper()

  if not download_files:
    return ''

  # Content of download config.
  result = []

  for resource_path in download_files:
    resource_name = os.path.basename(resource_path)
    resource_base_name = ParseResourceName(resource_name)[0]
    # Remove file extension (.gz).
    resource_base_name = os.path.splitext(resource_base_name)[0]

    channel = GetChannel(resource_base_name)
    url_name = urllib.quote(resource_name)
    sha1sum = file_utils.SHA1InBase64(resource_path)
    result.append(':'.join([channel, url_name, sha1sum]))

  return '\n'.join(result) + '\n'
