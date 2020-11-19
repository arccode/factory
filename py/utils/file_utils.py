# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""File-related utilities."""

import base64
import contextlib
import errno
import fnmatch
import glob
import gzip
import hashlib
import logging
import os
import pipes
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import zipfile
import zipimport

from . import platform_utils
from . import process_utils
from . import type_utils


# Block size in bytes for iteratively generating hashes of files.
_HASH_FILE_READ_BLOCK_SIZE = 1024 * 64  # 64kb


def TryMakeDirs(path):
  """Tries to create a directory and its parents.

  Doesn't ever raise an exception if it can't create the directory.
  """
  try:
    if not os.path.exists(path):
      os.makedirs(path)
  except Exception:
    pass


def MakeDirsUidGid(path, uid=-1, gid=-1, mode=0o777):
  """Recursive directory creation with specified uid, gid and mode.

  Like os.makedirs, but it also chown() and chmod() to the directories it
  creates.

  Args:
    path: Path to create recursively.
    uid: User id. -1 means unchanged.
    gid: Group id. -1 means unchanged.
    mode: Mode (numeric) of path. Default 0777.
  """
  logging.debug('MakeDirsUidGid %r', path)
  if not path:
    return
  if os.path.isdir(path):
    logging.debug('Path %s exists', path)
    return

  MakeDirsUidGid(os.path.dirname(path), uid, gid, mode)
  os.mkdir(path)
  os.chmod(path, mode)
  os.chown(path, uid, gid)
  logging.debug('mkdir %r with mode 0%o uid %r gid %r', path, mode, uid, gid)


class Glob:
  """A glob containing items to include and exclude.

  Properties:
    include: A single pattern identifying files to include.
    exclude: Patterns identifying files to exclude.  This can be
      None, or a single pattern, or a list of patterns.
  """

  def __init__(self, include, exclude=None):
    self.include = include
    if exclude is None:
      self.exclude = []
    elif isinstance(exclude, list):
      self.exclude = exclude
    elif isinstance(exclude, str):
      self.exclude = [exclude]
    else:
      raise TypeError('Unexpected exclude type %s' % type(exclude))

  def Match(self, root):
    """Returns files that match include but not exclude.

    Args:
      root: Root within which to evaluate the glob.
    """
    ret = []
    for f in glob.glob(os.path.join(root, self.include)):
      if not any(fnmatch.fnmatch(f, os.path.join(root, pattern))
                 for pattern in self.exclude):
        ret.append(f)
    return ret

  @staticmethod
  def Construct(loader, node):
    """YAML constructor."""
    value = loader.construct_mapping(node)
    type_utils.CheckDictKeys(value, ['include', 'exclude'])
    return Glob(value['include'], value.get('exclude', None))

  @staticmethod
  def Represent(representer, node):
    """YAML representer."""
    return representer.represent_mapping('!glob', dict(
        include=node.include, exclude=node.exclude))


def CreateTemporaryFile(**kwargs):
  """Gets an unopened temporary file.

  This is similar to UnopenedTemporaryFile except that CreateTemporaryFile is
  not a context manager and will not try to delete the allocated file, making it
  more convenient for unittest style programs to get temporary files in setUp
  and delete on tearDown.

  In comparison to tempfile.mkstemp, this function does not return an opened fd,
  thus avoiding potential file handle leaks.

  Args:
    Any allowable arguments to tempfile.NamedTemporaryFile (e.g., prefix,
      suffix, dir) except 'delete'.

  Returns:
    A file path.
  """
  assert kwargs.get('delete') is not True, 'CreateTemporaryFile never deletes.'
  kwargs['delete'] = False
  with tempfile.NamedTemporaryFile(**kwargs) as f:
    path = f.name
  return path


@contextlib.contextmanager
def UnopenedTemporaryFile(**kwargs):
  """Yields an unopened temporary file.

  The file is not opened, and it is deleted when the context manager
  is closed if it still exists at that moment.

  Args:
    Any allowable arguments to tempfile.NamedTemporaryFile (e.g., prefix,
      suffix, dir).
  """
  path = CreateTemporaryFile(**kwargs)
  try:
    yield path
  finally:
    if os.path.exists(path):
      os.unlink(path)


@contextlib.contextmanager
def TempDirectory(**kwargs):
  """Yields an temporary directory.

  The temp directory is deleted when the context manager is closed if it still
  exists at that moment.

  Args:
    Any allowable arguments to tempfile.mkdtemp (e.g., prefix,
      suffix, dir).
  """
  path = tempfile.mkdtemp(**kwargs)
  try:
    yield path
  finally:
    if os.path.exists(path):
      shutil.rmtree(path)


def ReadLines(filename, dut=None):
  """Returns a file as list of lines.

  It is used to facilitate unittest.

  Args:
    filename: file name.

  Returns:
    List of lines of the file content. None if IOError.
  """
  try:
    if dut is None:
      with open(filename, encoding='utf-8') as f:
        return f.readlines()
    else:
      return dut.ReadSpecialFile(filename).splitlines(True)
  except Exception:
    logging.exception('Cannot read file "%s"', filename)
    return None


def TryUnlink(path):
  """Unlinks a file only if it exists.

  Args:
    path: File to attempt to unlink.

  Raises:
    Any OSError thrown by unlink (except ENOENT, which means that the file
    simply didn't exist).
  """
  try:
    os.unlink(path)
  except OSError as e:
    if e.errno != errno.ENOENT:
      raise


def ReadFile(path, encoding='utf-8'):
  """Reads data from a file.

  Args:
    path: The path of the file to read.
    encoding: Same param as open(). Set to None for binary mode.
  """
  with open(path, mode='r' if encoding else 'rb', encoding=encoding) as f:
    return f.read()


def TailFile(path, max_length=5 * 1024 * 1024, dut=None):
  """Returns the last n bytes of the given file.

  Args:
    path: path to the file to read
    max_length: Maximum characters of messages.
    dut: a cros.factory.device.device_types.DeviceInterface instance, None for
         local.
  """
  if dut:
    data = dut.CheckOutput(['tail', '-c', str(max_length), path])
    size = int(dut.CheckOutput(['stat', '--printf=%s', path]))
    offset = size - len(data.encode('utf-8'))
  else:
    offset = max(0, os.path.getsize(path) - max_length)
    with open(path, encoding='utf-8') as f:
      f.seek(offset)
      data = f.read()

  if offset:
    # Skip the first (probably incomplete) line
    skipped_line, unused_sep, data = data.partition('\n')
    offset += len(skipped_line) + 1
    data = ('<truncated %d bytes>\n' % offset) + data
  return data


def WriteFile(path, data, encoding='utf-8', log=False):
  """Writes a value to a file.

  Args:
    path: The path to write to.
    data: The value to write.  This may be any type and is stringified with
        str(). If you need to write bytes, you should set encoding to None.
    encoding: Same param as open(). Set to None for binary mode.
    log: Whether to log path and data.
  """
  if log:
    logging.info('Writing %r to %s', data, path)

  if encoding:
    data = data if isinstance(data, str) else str(data)
  elif not isinstance(data, bytes):
    raise TypeError('Given data must be in type of `bytes` in binary mode')

  with open(path, mode='w' if encoding else 'wb', encoding=encoding) as f:
    f.write(data)


def TouchFile(path):
  """Touches a file.

  Args:
    path: The path to touch.
  """
  with open(path, 'a'):
    os.utime(path, None)


def ReadOneLine(filename):
  """Returns the first line as a string from the given file."""
  with open(filename, 'r') as f:
    return f.readline().rstrip('\n')


def SetFileExecutable(path):
  """Sets the file's executable bit.

  Args:
    path: The file path.
  """
  st = os.stat(path)
  os.chmod(path, st.st_mode | stat.S_IXUSR)


def CopyFileSkipBytes(in_file_name, out_file_name, skip_size):
  """Copies a file and skips the first N bytes.

  Args:
    in_file_name: input file_name.
    out_file_name: output file_name.
    skip_size: number of head bytes to skip. Should be smaller than
        in_file size.

  Raises:
    ValueError if skip_size >= input file size.
  """
  in_file_size = os.path.getsize(in_file_name)
  if in_file_size <= skip_size:
    raise ValueError('skip_size: %d should be smaller than input file: %s '
                     '(size: %d)' % (skip_size, in_file_name, in_file_size))

  _CHUNK_SIZE = 4096
  with open(in_file_name, 'rb') as in_file:
    with open(out_file_name, 'wb') as out_file:
      in_file.seek(skip_size)
      shutil.copyfileobj(in_file, out_file, _CHUNK_SIZE)


def Sync(log=True):
  """Calls 'sync'."""
  process_utils.Spawn(['sync'], log=log, check_call=True)


def GetFileSizeInBytes(path, follow_link=False, dut=None):
  if dut:
    cmd = ['stat', '-c', '%F\n%s'] + (['-L'] if follow_link else []) + [path]
    output = dut.CallOutput(cmd)
    (file_type, size) = output.splitlines()

    if file_type in ('block special file', 'block device'):
      return int(dut.CallOutput(['blockdev', '--getsize64', path]))
    # For other files, just returns what we got from stat
    return int(size)

  with open(path, 'rb') as f:
    f.seek(0, os.SEEK_END)
    return f.tell()


def IsGzippedFile(path):
  """Check if the given file is gzipped. (Not 100% accurate)

  Args:
    path: path to the file to check.

  Returns:
    True if it looks like a gzipped file.
  """
  with open(path, 'rb') as f:
    return f.read(2) == b'\x1f\x8b'


@contextlib.contextmanager
def GunzipSingleFile(gzip_path, output_path=None):
  """Extracts a gzip file which contains only one file.

  Args:
    gzip_path: Path to gzipped file.
    output_path: Path to extract. None to use a temporary output file.

  Yields:
    Path to extracted file. If output_path is omitted, yields a temporary file
    path. Note that it deletes the temporary file after leaving the context.
  """
  MAX_CHUNK_SIZE = 10 * 1024 * 1024

  is_temp_file = not output_path
  if not output_path:
    output_path = CreateTemporaryFile(prefix='GunzipSingleFile_')

  with open(output_path, 'wb') as output_file:
    with gzip.open(gzip_path, 'rb') as input_file:
      while True:
        chunk = input_file.read(MAX_CHUNK_SIZE)
        if not chunk:
          break
        output_file.write(chunk)

  try:
    yield output_path
  finally:
    if is_temp_file and os.path.exists(output_path):
      os.unlink(output_path)


class ExtractFileError(Exception):
  """Failure of extracting compressed file."""


def GetCompressor(file_format, allow_parallel=True):
  """Returns a compressor program for given file format.

  Args:
    file_format: A string for compression format (bz2, gz, xz).
    allow_parallel: True to return best compressor in multi-thread.

  Returns:
    A string for compressor program name, or None if nothing found.
  """
  program_map = {
      'gz': ['pigz', 'gzip'],
      'bz2': ['lbzip2', 'pbzip2', 'bzip2'],
      'xz': ['pixz', 'xz'],
  }
  program_list = program_map[file_format]
  if not allow_parallel:
    program_list = program_list[-1:]
  for program in program_list:
    if os.system('type %s >/dev/null 2>&1' % program) == 0:
      return program
  return None


def ExtractFile(compressed_file, output_dir, only_extracts=None,
                overwrite=True, quiet=False, use_parallel=False,
                exclude=None):
  """Extracts compressed file to output folder.

  Args:
    compressed_file: Path to a compressed file.
    output_dir: The path to the output directory.
    only_extracts: An optional list of files to extract from the given
      compressed file.
    overwrite: Whether to overwrite existing files without prompt.  Defaults to
      True.
    quiet: Whether to suppress output.
    use_parallel: Allow using parallel compressor to shorten execution time.
    exclude: a list of file patterns to exclude.

  Raises:
    ExtractFileError if the method fails to extract the file.
  """

  if not os.path.exists(compressed_file):
    raise ExtractFileError('Missing compressed file %r' % compressed_file)
  if not os.access(compressed_file, os.R_OK):
    raise ExtractFileError('Permission denied reading compressed file %r' %
                           compressed_file)
  TryMakeDirs(output_dir)
  logging.info('Extracting %s to %s', compressed_file, output_dir)
  only_extracts = type_utils.MakeList(only_extracts) if only_extracts else []
  if only_extracts:
    logging.info('Extracts only file(s): %s', only_extracts)

  if compressed_file.endswith('.zip'):
    overwrite_opt = ['-o'] if overwrite else []
    quiet_opt = ['-qq'] if quiet else []
    exclude_opt = ['-x'] + exclude if exclude else []
    cmd = (['unzip'] + overwrite_opt + quiet_opt + [compressed_file] +
           ['-d', output_dir] +
           only_extracts + exclude_opt)
  else:
    formats = (
        (['.tar'], None),
        (['.tar.gz', '.tgz'], 'gz'),
        (['.tar.bz2', '.tbz2'], 'bz2'),
        (['.tar.xz', '.txz'], 'xz'))
    unsupported = True
    for suffixes, file_format in formats:
      if any(compressed_file.endswith(suffix) for suffix in suffixes):
        unsupported = False
        cmd = ['tar', '-xf', compressed_file, '-C', output_dir]
        if not overwrite:
          cmd += ['--keep-old-files']
        if not quiet:
          cmd += ['-vv']
        if use_parallel:
          cmd += ['-I', GetCompressor(file_format, use_parallel)]
        if exclude:
          cmd += ['--exclude=%s' % e for e in exclude]
        cmd += only_extracts
        break
    if unsupported:
      raise ExtractFileError('Unsupported compressed file: %s' %
                             compressed_file)

  return process_utils.Spawn(cmd, log=True, check_call=True)


def ForceSymlink(target, link_name):
  """Makes a symlink to target even if link_name already exists.

  Args:
    target: target file path
    link_name: symlink name.

  Raises:
    Exception: target is missing
    OSError: failed to make symlink
  """
  # target can be either a absolute path or a relative path.
  real_target = os.path.join(os.path.dirname(link_name), target)
  if not os.path.exists(real_target):
    raise Exception('Missing symlink target: ' + real_target)
  TryUnlink(link_name)
  os.symlink(target, link_name)


def CheckPath(path, description=None):
  """Checks if the path exists.

  It raises IOError with default message "No such file or directory" if
  path not found. If file_type is given, the error message becomes:
  "Missing file_type".

  Args:
    path: path to check.
    description: the description of the path to check, e.g. "factory bundle".

  Raises:
    IOError
  """
  if not os.path.exists(path):
    message = ('Missing ' + description if description else
               'No such file or directory')
    raise IOError(errno.ENOENT, message, path)


def AtomicCopy(source, dest, mode=None):
  """Copies source file to dest in an atomic manner.

  It copies source to a temporary file first. Then renames the temp file to
  dest. It avoids interrupting others reading the dest file while copying.

  Args:
    source: source filename.
    dest: destination filename.
    mode: new file mode if specified.
  """
  CheckPath(source, description='source')
  with UnopenedTemporaryFile(prefix='atomic_copy_') as temp_path:
    shutil.copy2(source, temp_path)
    if mode is not None:
      os.chmod(temp_path, mode)
    try:
      os.rename(temp_path, dest)
    except OSError as err:
      # Use shutil to workaround Cross-device link error.
      if err.errno != errno.EXDEV:
        raise
      shutil.move(temp_path, dest)


def FileHash(path, algorithm, block_size=_HASH_FILE_READ_BLOCK_SIZE):
  """Calculates given hash of a local file.

  From: http://stackoverflow.com/questions/1742866/compute-crc-of-file-in-python

  Args:
    path: Local path of the file.
    algorithm: Name of algorithm to use.  Should be one of algorithms available
               in hashlib.algorithms.  For example: md5, sha1

  Returns:
    Hashlib object representing the given file.
  """
  file_hash = hashlib.new(algorithm)
  with open(path, 'rb') as f:
    for chunk in iter(lambda: f.read(block_size), b''):
      file_hash.update(chunk)
  return file_hash


def MD5InHex(path):
  """Returns hex-encoded MD5 sum of given file."""
  return FileHash(path, 'md5').hexdigest()


def MD5InBase64(path):
  """Returns base64-encoded MD5 sum of given file."""
  md5_sum = base64.standard_b64encode(FileHash(path, 'md5').digest())
  return md5_sum.decode('utf-8')


def SHA1InHex(path):
  """Returns hex-encoded SHA1 sum of given file."""
  return FileHash(path, 'sha1').hexdigest()


def SHA1InBase64(path):
  """Returns base64-encoded SHA1 sum of given file."""
  sha1_sum = base64.standard_b64encode(FileHash(path, 'sha1').digest())
  return sha1_sum.decode('utf-8')


# Legacy function names for backwards compatibility.
# TODO(kitching): Remove these functions after M56 stable release.
Md5sumInHex = MD5InHex
B64Sha1 = SHA1InBase64


class FileLockTimeoutError(Exception):
  """Timeout error for FileLock."""


class FileLock:
  """An exclusive lock implemented with file lock.

  The lock is designed to work either in one process or across multiple
  processes. Call Acquire() to acquire the file lock. The file lock is release
  either by calling Release() manually, or when the process is terminated.

  Args:
    lockfile: The path to the file used as lock.
    timeout_secs: The maximum duration in seconds to wait for the lock, or None
      to fail immediately if unable to acquire lock.
    retry_secs: seconds to wait between retries when timeout_secs is not None.
  """

  def __init__(self, lockfile, timeout_secs=None, retry_secs=0.1):
    self._lockfile = lockfile
    self._timeout_secs = timeout_secs
    self._retry_secs = retry_secs
    self._fd = None
    self._locked = False
    self._sys_lock = platform_utils.GetProvider('FileLock')

  def Acquire(self):
    self._fd = os.open(self._lockfile, os.O_RDWR | os.O_CREAT)

    remaining_secs = self._timeout_secs
    while True:
      try:
        self._sys_lock(self._fd, is_exclusive=True, is_blocking=False)
        self._locked = True
        logging.debug('%s (%d) locked by %s',
                      self._lockfile, self._fd, os.getpid())
        break
      except IOError:
        if self._timeout_secs is not None:
          # We don't want to use real system time because the sleep may
          # be longer due to system busy or suspend/resume.
          time.sleep(self._retry_secs)
          remaining_secs -= self._retry_secs
          if remaining_secs < 0:
            raise FileLockTimeoutError(
                'Could not acquire file lock of %s in %s second(s)' %
                (self._lockfile, self._timeout_secs))
        else:
          raise

  def Release(self):
    if self._locked:
      self._sys_lock(self._fd, do_lock=False)
      self._locked = False
      logging.debug('%s (%d) unlocked by %s',
                    self._lockfile, self._fd, os.getpid())
    if self._fd:
      os.close(self._fd)
      self._fd = None

  def __enter__(self):
    return self.Acquire()

  def __exit__(self, *args, **kwargs):
    self.Release()


def WriteWithSudo(file_path, content):
  """Writes content to file_path with sudo=True.

  Args:
    file_path: The path to write to.
    content: The content to write.
  """
  # Write with sudo, since only root can write this.
  process = process_utils.Spawn(
      'cat > %s' % pipes.quote(file_path), sudo=True,
      stdin=subprocess.PIPE, shell=True)
  process.stdin.write(content)
  process.stdin.close()
  if process.wait():
    raise RuntimeError('Unable to write %s' % file_path)


def GlobSingleFile(pattern):
  """Returns the name of the single file matching a pattern.

  Args:
    pattern: A pattern that should match exactly one file.

  Raises:
    ValueError if the pattern matches zero or >1 files.
  """
  matches = glob.glob(pattern)
  if len(matches) != 1:
    raise ValueError('Expected one match for %s but got %s' %
                     (pattern, matches))

  return matches[0]


def ExtractFromPar(par_file, src, dest='.'):
  """Extracts a file from a Python archive.

  Args:
      par_file: The Python archive to extract file from.
      src: The file component to extract from the Python archive.
      dest: The destination path to extract file to.
  """
  par = zipfile.ZipFile(par_file)
  par.extract(src, dest)


def LoadModuleResource(path):
  """Loads a file that lives in same place with python modules.

  This is very similar to ReadFile except that the path can be a real file or
  virtual path inside Python ZIP (PAR).

  Args:
      path: The path to the file.

  Returns:
      Contents of resource in path, or None if the resource cannot be found.
  """
  if os.path.exists(path):
    return ReadFile(path)

  try:
    file_dir = os.path.dirname(path)
    file_name = os.path.basename(path)
    importer = zipimport.zipimporter(file_dir)
    zip_path = os.path.join(importer.prefix, file_name)
    return importer.get_data(zip_path)
  except Exception:
    pass

  return None


def HashFiles(root, path_filter=None, hash_function=hashlib.sha1):
  """Returns a dictionary of the hashes of files' contents.

  The root directory is recursively walked. Each file is read, its
  contents hashed, and the result placed in a dict. The dict's keys
  are paths to the files relative to the root, and values are the
  calculated hashes.

  Symbolic links are ignored.

  For instance, if the directory tree is:

    root/
      a/
        b.txt
      c.txt

  ...then HashFiles('root') returns a dict like this:

    {'a/b.txt': 'e9d71f5ee7c92d6dc9e92ffdad17b8bd49418f98',
     'c.txt':   '84a516841ba77a5b4648de2cd0dfcb30ea46dbb4'}

  Args:
    root: Root directory to walk with os.walk.
    path_filter: An optional predicate specifying which files to process.
        This function is invoked with a single argument (the path to a
        file) and should return True if the file is to be considered,
        or File if not.  If the filter is None, all files are included.
    hash_function: The hash function to use. This function is invoked with
        a single argument (the contents of a file) and should return the
        value to use as a hash.  (If the returned object has a hexdigest()
        method, as do hash functions like hashlib.sha1, it is invoked.)
  """
  ret = {}
  for dirpath, _, filenames in os.walk(root):
    for f in filenames:
      path = os.path.join(dirpath, f)
      if os.path.islink(path):
        # Skip symbolic links
        continue

      # Apply path filter, if provided
      if path_filter and not path_filter(path):
        continue

      data = ReadFile(path, encoding=None)
      hash_value = hash_function(data)
      # If it has hexdigest() (e.g., we were called with
      # hash_function=hashlib.sha1), call it
      try:
        hash_value = hash_value.hexdigest()
      except AttributeError:
        pass

      ret[os.path.relpath(path, root)] = hash_value
  return ret


SOURCE_HASH_FUNCTION_NAME = 'sha1prefix'


def HashSourceTree(py_path):
  """Calculates hashes of sources in a source tree using HashFiles.

  Only .py files are considered.  The first four bytes of the SHA1
  hash is used as a hash function.

  Args:
    py_path: Directory containing .py sources.

  Returns:
    See HashFiles.
  """
  hashes = HashFiles(
      py_path,
      lambda path: path.endswith('.py'),
      # Use first 4 bytes of SHA1
      hash_function=lambda data: hashlib.sha1(data).hexdigest()[0:8])
  if not hashes:
    raise RuntimeError('No sources found in %s' % py_path)

  return dict(
      # Log hash function used, just in case we ever want to change it
      hash_function=SOURCE_HASH_FUNCTION_NAME,
      hashes=hashes)


def HashPythonArchive(par_path):
  hashes = HashFiles(
      os.path.dirname(par_path),
      lambda path: path == par_path,
      # Use first 4 bytes of SHA1
      hash_function=lambda data: hashlib.sha1(data).hexdigest()[0:8])
  if not hashes:
    raise RuntimeError('No sources found at %s' % par_path)

  return dict(
      # Log hash function used, just in case we ever want to change it
      hash_function=SOURCE_HASH_FUNCTION_NAME,
      hashes=hashes)


class FileLockContextManager:
  """Represents a file lock in context manager's form

  Provides two different levels of lock around the associated file.
  - For accessing a file in the same process, please make sure all the access
  goes through this class, the internal lock will guarantee no racing with that
  file.
  - For accessing a file across different process, this class will put an
  exclusive advisory lock during "with" statement.

  Args:
    path: Path to the file.
    mode: Mode used to open the file.
  """

  def __init__(self, path, mode):
    self.path = path
    self.mode = mode
    self.opened = False
    self.file = None
    self._lock = threading.Lock()
    self._filelock = platform_utils.GetProvider('FileLock')

  def __enter__(self):
    """Locks the associated file."""
    self._lock.acquire()
    self._OpenUnlocked()
    self._filelock(self.file.fileno(), True)
    return self.file

  def __exit__(self, ex_type, value, tb):
    """Unlocks the associated file."""
    del ex_type, value, tb
    self._filelock(self.file.fileno(), False)
    self._lock.release()

  def Close(self):
    """Closes associated file."""
    if self.file:
      with self._lock:
        self.opened = False
        self.file.close()
        self.file = None

  def _OpenUnlocked(self):
    parent_dir = os.path.dirname(self.path)
    if not os.path.exists(parent_dir):
      try:
        os.makedirs(parent_dir)
      except OSError:
        # Maybe someone else tried to create it simultaneously
        if not os.path.exists(parent_dir):
          raise

    if self.opened:
      return

    self.file = open(self.path, self.mode)
    self.opened = True


def SyncDirectory(dir_path):
  """Flush and sync directory on file system.

  Python 2.7 does not support os.sync() so this is the closest way to flush file
  system meta data changes.
  """
  try:
    dir_fd = os.open(dir_path, os.O_DIRECTORY)
    os.fsync(dir_fd)
  except Exception:
    logging.exception('Failed syncing in directory: %s', dir_path)
  finally:
    try:
      os.close(dir_fd)
    except Exception:
      pass


@contextlib.contextmanager
def AtomicWrite(path, binary=False, fsync=True):
  """Atomically writes to the given file.

  Uses write-rename strategy with fsync to atomically write to the given file.

  Args:
    binary: Whether or not to use binary mode in the open() call.
    fsync: Flushes and syncs data to disk after write if True.
  """
  # TODO(kitching): Add Windows support.  On Windows, os.rename cannot be
  #                 used as an atomic operation, since the rename fails when
  #                 the target already exists.  Additionally, Windows does not
  #                 support fsync on a directory as done below in the last
  #                 conditional clause.  Some resources suggest using Win32
  #                 API's MoveFileEx with MOVEFILE_REPLACE_EXISTING mode,
  #                 although this relies on filesystem support and won't work
  #                 with FAT32.
  mode = 'wb' if binary else 'w'
  path_dir = os.path.abspath(os.path.dirname(path))
  path_file = os.path.basename(path)
  assert path_file != ''  # Make sure path contains a file.
  with UnopenedTemporaryFile(prefix='%s_atomicwrite_' % path_file,
                             dir=path_dir) as tmp_path:
    with open(tmp_path, mode) as f:
      yield f
      if fsync:
        f.flush()
        os.fdatasync(f.fileno())
    # os.rename is an atomic operation as long as src and dst are on the
    # same filesystem.
    os.rename(tmp_path, path)
  if fsync:
    SyncDirectory(path_dir)


def SymlinkRelative(target, link_path, base=None, force=False):
  """Makes a relative symlink to target

  If base is not None, only make symlink relative if both link_path and target
  are under the absolute path given by base.

  If force is True, try to unlink link_path before doing symlink.

  If target is a relative path, it would be directly used as argument of
  os.symlink, and base argument is ignored.

  This function does not check the existence of target.

  Args:
    target: target file path.
    link_path: symlink path, can be absolute or relative to current dir.
    base: only make symlink relative if both target and link_path are under this
          path.
    force: whether to force symlink even if link_path exists.

  Raises:
    OSError: failed to make symlink
  """
  link_path = os.path.abspath(link_path)

  if os.path.isabs(target):
    if base is not None and base[-1] != '/':
      # Make sure base ends with a /
      base += '/'
    if base is None or os.path.commonprefix([base, target, link_path]) == base:
      target = os.path.relpath(target, os.path.dirname(link_path))

  if force:
    TryUnlink(link_path)

  os.symlink(target, link_path)
