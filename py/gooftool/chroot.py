# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import contextlib
from distutils import sysconfig
import logging
import os

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import process_utils

DEFAULT_ETC_ISSUE = """
You are now in tmp file system created by gooftool.chroot.Chroot.
Log files can be found under /tmp, /mnt/stateful_partition/unencrypted.
"""

class TmpChroot(object):
  """Create a tmpfs with necessary files and chroot to it.

  Please refer to Chroot.__init__ to see what it will do.
  """

  def __init__(self, new_root, binary_list=None, file_dir_list=None,
               etc_issue=None, logfile=None, size='1024M'):
    """The constructor.

    Args:
      new_root: Path to the new root, this should be a directory, a tmpfs will
          be mounted at this point.
      binary_list: Executable or libraries that are required in the new root,
          libraries they depend on will also be copied. For common utilities,
          `busybox` and `python` are always included in the list.
      file_dir_list: Files and dirs that are required in the new root.
          Since `python` is included in `binary_list`, python lib are included
          in this list.
      etc_issue: A string that will be saved in `<new_root>/etc/issue`.
      logfile: Path to the log file, default will be '/tmp/gooftool.chroot.log'
      size: A string for size of the tmpfs, default '1024M'
    """
    self.new_root = os.path.realpath(new_root)
    assert self.new_root != '/', 'new root cannot be /'

    self.binary_list = binary_list if binary_list is not None else []
    self.file_dir_list = file_dir_list if file_dir_list is not None else []
    self.etc_issue = etc_issue if etc_issue is not None else DEFAULT_ETC_ISSUE
    self.logger = logging.getLogger('Chroot')
    if logfile is not None:
      file_handler = logging.FileHandler(logfile)
      file_handler.setLevel(logging.NOTSET)  # log everything
      self.logger.addHandler(file_handler)
    self.size = size

  def _GetLoadedLibrary(self):
    # we assume that all memory mapped files are shared libraries
    command = ['lsof', '-p', str(os.getpid()), '-a', '-d', 'mem']
    return [line.split()[-1]
            for line in process_utils.SpawnOutput(command).splitlines()[1:]]

  def InitializeNewRoot(self):
    """Initialize the new root.

    `self.binary_list` and `self.file_dir_list` are copied to new root.
    Special file systems 'dev', 'proc', 'sys', 'run' bound to new root.
    """
    self.logger.debug('InitializeNewRoot')

    # create tmpfs
    process_utils.Spawn(['mount', '-n', '-t', 'tmpfs',
                         '-o', 'size=' + self.size,
                         '-o', 'mode=755',
                         'tmpfs', self.new_root],
                        check_call=True)

    self.logger.debug('create tmpfs layout')
    tmpfs_layout_dirs = [os.path.join(self.new_root, subdir)
                         for subdir in ['bin', 'dev', 'etc', 'lib', 'log',
                                        'mnt/stateful_partition', 'proc',
                                        'root', 'sys', 'tmp', 'var']]
    process_utils.Spawn(['mkdir', '-p'] + tmpfs_layout_dirs, check_call=True)
    # use symbolic links to make /usr/local/bin, /bin/, /usr/bin same as /sbin
    process_utils.Spawn(['ln', '-s', '.', os.path.join(self.new_root, 'usr')],
                        check_call=True)
    process_utils.Spawn(['ln', '-s', '.', os.path.join(self.new_root, 'local')],
                        check_call=True)
    process_utils.Spawn(['ln', '-s', 'bin',
                         os.path.join(self.new_root, 'sbin')],
                        check_call=True)
    process_utils.Spawn(['ln', '-s', '/run',
                         os.path.join(self.new_root, 'var', 'run')],
                        check_call=True)
    process_utils.Spawn(['ln', '-s', '/run/lock',
                         os.path.join(self.new_root, 'var', 'lock')],
                        check_call=True)

    self.logger.debug('copy necessary files and dirs')
    files_dirs = self.file_dir_list + [
        sysconfig.get_python_lib(standard_lib=True),
        sysconfig.get_python_inc()]
    files_dirs = filter(os.path.exists, files_dirs)
    process_utils.Spawn(('tar -h -c %s | '
                         'tar -C %s -x --skip-old-files' %
                         (' '.join(files_dirs), self.new_root)),
                        shell=True, call=True, log=True)

    self.logger.debug('copy necessary binaries')
    bin_deps = self.binary_list + ['python2', 'busybox']
    bin_deps += self._GetLoadedLibrary()

    bin_paths = [(k, process_utils.SpawnOutput(['which', k]).strip())
                 for k in bin_deps]
    self.logger.warn('following binaries are not found: %s',
                     [k for (k, v) in bin_paths if not v])
    # remove binaries that are not found
    bin_paths = {k: v for (k, v) in bin_paths if v}
    # copy binaries and their dependencies
    process_utils.Spawn(
        ('tar -ch $(lddtree -l %s 2>/dev/null | sort -u) | '
         'tar -C %s -x --skip-old-files' %
         (' '.join(bin_paths.values()), self.new_root)),
        check_call=True, shell=True, log=True)

    # install busybox for common utilities
    process_utils.Spawn(
        [os.path.join(self.new_root, 'bin', 'busybox'), '--install',
         os.path.join(self.new_root, 'bin')], check_call=True, log=True)

    # create /etc/issue
    open(os.path.join(self.new_root, 'etc', 'issue'), 'w').write(self.etc_issue)

    self.logger.debug('rebind mount points')
    rebind_dirs = ['dev', 'proc', 'sys', 'run']
    for node in rebind_dirs:
      src_dir = os.path.join('/', node)
      dst_dir = os.path.join(self.new_root, node)
      if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
      process_utils.Spawn(['mount', '--rbind', src_dir, dst_dir],
                          check_call=True)
    process_utils.Spawn(['cp', '-fd', '/etc/mtab',
                         os.path.join(self.new_root, 'etc', 'mtab')],
                        check_call=True)

  def Chroot(self):
    """Change root to `self.new_root`.

    This function should be used with 'with' statement::

      with tmpchroot.Chroot():
        # do something inside chroot

    The tmpfs will be mount and initialized before entering the context, and
    will be cleared and unmounted after leaving the context.
    """
    return self._InvokeChroot(pivot_root=False, old_root=None)

  def PivotRoot(self, old_root='old_root'):
    """Change the root filesystem with pivot_root.

    This function will moves the current root file system to `old_root` and
    makes `self.new_root` the new root file system.
    This function should be used with 'with' statement::

      with tmpchroot.PivotRoot(old_root):
        # now tmpchroot.new_root is mounted at root ('/'), and the old root file
        # system is at /`old_root`

    The file system will be reset when leaving the context. That is, current
    root file system will be moved back to root and tmpfs will be cleared and
    unmounted.
    """
    return self._InvokeChroot(pivot_root=True, old_root=old_root)

  @contextlib.contextmanager
  def _InvokeChroot(self, pivot_root, old_root):
    self.logger.debug('Chroot pivot_root=%r, old_root=%r', pivot_root, old_root)

    assert (not pivot_root) or old_root, (
        'old_root must be given when pivot root')

    real_root = os.open('/', os.O_RDONLY)  # cache the old root

    self.InitializeNewRoot()

    os.chdir(self.new_root)
    if pivot_root:
      old_root_path = os.path.join(self.new_root, old_root)
      assert not os.path.lexists(old_root_path), '%s already exists' % old_root
      os.makedirs(old_root_path)
      process_utils.Spawn(['pivot_root', '.', old_root])

    os.chroot('.')
    self.logger.debug('changed root to %s', self.new_root)

    try:
      yield
    finally:
      if pivot_root:
        os.chdir(os.path.join('/', old_root))
        process_utils.Spawn(['pivot_root', '.', self.new_root[1:]])
        os.chroot('.')
      else:
        os.fchdir(real_root)
        os.chroot('.')

      self.ResetNewRoot()

  def ResetNewRoot(self):
    """unmount mounted tmpfs at new root."""
    process_utils.Spawn(['umount', '-R', self.new_root], check_call=True)
