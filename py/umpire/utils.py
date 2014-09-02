# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Umpire utility classes."""

import logging
import os
import shutil
from twisted.internet import defer

import factory_common  # pylint: disable=W0611
from cros.factory.common import AttrDict, Singleton
from cros.factory.umpire.common import GetHashFromResourceName
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


class Registry(AttrDict):

  """Registry is a singleton class that inherits from AttrDict.

  Example:
    config_file = Registry().get('active_config_file', None)
    Registry().extend({
      'abc': 123,
      'def': 456
    })
    assertEqual(Registry().abc, 123)
  """
  __metaclass__ = Singleton


def ConcentrateDeferreds(deferred_list):
  """Collects results from list of deferreds.

  CollectDeferreds() returns a deferred object that fires error callback
  on first error. And the original failure won't propagate back to original
  deferred object's next error callback.

  Args:
    deferred_list: Iterable of deferred objects.

  Returns:
    Deferred object that fires error on any deferred_list's errback been
    called. Its callback will be trigged when all callback results are
    collected. The gathered result is a list of deferred object callback
    results.
  """
  return defer.gatherResults(deferred_list, consumeErrors=True)


def UnpackFactoryToolkit(env, toolkit_resource, device_toolkit=True,
                         run_as=None, mode=0750):
  """Unpacks factory toolkit in resources to toolkits/hash directory.

  Note that if the destination directory already exists, it doesn't unpack.

  Args:
    env: UmpireEnv object.
    toolkit_resource: Path to factory toolkit resources.
    device_toolkit: True to unpack to env.device_toolkits_dir; otherwise,
      env.server_toolkits_dir.
    run_as: (uid, gid) unpacks using specified user/group. Default None means
      no uid, gid changes.
    mode: Directory permission (numerical, refer os.chmod) for newly unpacked
      toolkit. Default 0750 ('rwxr-x---').

  Returns:
    Directory to unpack. None if toolkit_resource is invalid.
  """
  def RunAs():
    """Demotes user.group to uid.gid specified in run_as param.

    It is used to execute a command as another user.
    """
    os.umask(022)
    if not run_as:
      return
    uid, gid = run_as
    os.setgid(gid)
    os.setuid(uid)

  if not isinstance(toolkit_resource, str) or not toolkit_resource:
    logging.error('Invalid toolkit_resource %r', toolkit_resource)
    return None

  toolkit_path = env.GetResourcePath(toolkit_resource)
  toolkit_hash = GetHashFromResourceName(toolkit_resource)
  unpack_dir = os.path.join(
      env.device_toolkits_dir if device_toolkit else env.server_toolkits_dir,
      toolkit_hash)
  if os.path.isdir(unpack_dir):
    logging.info('UnpackFactoryToolkit destination dir already exists: %s',
                 unpack_dir)
    return unpack_dir

  if run_as:
    uid, gid = run_as
  else:
    uid, gid = -1, -1

  # Extract to temp directory first then move the directory to prevent
  # keeping a broken toolkit.
  with file_utils.TempDirectory() as temp_dir:
    if run_as:
      os.chown(temp_dir, uid, gid)

    process_utils.Spawn([toolkit_path, '--noexec', '--target', temp_dir],
                        preexec_fn=RunAs, check_call=True, log=True)

    # Create toolkit directory's base directory first.
    unpack_dir_base = os.path.split(unpack_dir)[0]
    if not os.path.isdir(unpack_dir_base):
      file_utils.MakeDirsUidGid(unpack_dir_base, uid, gid, mode=mode)
    else:
      logging.debug('unpack_dir_base %r already exists', unpack_dir_base)

    # Use shutil.move() instead of os.rename(). os.rename calls OS
    # rename() function. And under Linux-like OSes, this system call
    # creates and removes hardlink, that only works when source path and
    # destination path are both on same filesystem.
    shutil.move(temp_dir, unpack_dir)
    os.chmod(unpack_dir, mode)
    logging.debug('Factory toolkit extracted to %s', unpack_dir)

  # TODO(deanliao): figure out if the permission is too loose.
  # Give group/other rX permision on all files/directories under unpack_dir.
  process_utils.Spawn(['chmod', '-R', 'og+rX', unpack_dir], check_call=True,
                      log=True)

  # Inject MD5SUM in extracted toolkit as umpire read only.
  md5sum_path = os.path.join(unpack_dir, 'usr', 'local', 'factory', 'MD5SUM')
  with open(md5sum_path, 'w') as f:
    f.write(toolkit_hash)
  os.chmod(md5sum_path, 0440)
  if run_as:
    os.chown(md5sum_path, uid, gid)
  logging.debug('%r generated', md5sum_path)

  return unpack_dir


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
