# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from collections import namedtuple
import pipes

from cros.factory.device import device_types
from cros.factory.utils import debug_utils


class Toybox(device_types.DeviceComponent):
  """A python wrapper for http://www.landley.net/toybox/.

  Toybox combines many common Linux command line utilities together into a
  single BSD-licensed executable. It's simple, small, fast, and reasonably
  standards-compliant (POSIX-2008 and LSB 4.1).

  This wrapper virtualized its command and parameters so tests can be written
  in a portable way.
  """

  # The data structures used by sub commands.

  DISK_FREE_TUPLE = namedtuple(
      'DiskFreeTuple', 'filesystem kblocks used available use_pct mounted_on')

  MEM_FREE_TUPLE = namedtuple(
      'MemoryFreeTuple',
      ('mem_total mem_used mem_free mem_shared mem_buffers ' +
       # The second line refers to +/- buffers/cache.
       'mem_min_used mem_max_free ' +
       'swap_total swap_used swap_free'))

  MOUNT_TUPLE = namedtuple(
      'MountTuple', 'device path type options')

  UPTIME_TUPLE = namedtuple(
      'UptimeTuple',
      'current_time uptime users loadavg_1min loadavg_5min loadavg_15min')

  _PROVIDER_MAP = {'*': 'toybox'}
  """Map of providers for each command.

  You can override this mapping to use different provider for different
  commands.  For example, if you'd like to use dd from busybox, df from system,
  and maybe all others from toolbox, then you should create a toybox instance
  by:

      toybox = Toybox(
          dut, provider_map={'*': 'toolbox', 'dd': 'busybox', 'df': None})
  """

  def __init__(self, dut, sudo=False, provider_map=None):
    """Constructor

    Args:
      dut: a DUT instance.
      sudo: use sudo(8) to execute each command or not.
      provider_map: override default provider map, see Toybox._PROVIDER_MAP for
        more details.
    """
    super(Toybox, self).__init__(dut)
    self._sudo = sudo
    self._provider_map = provider_map or Toybox._PROVIDER_MAP

  def _BuildCommand(self, *args):
    """Builds the real toybox command to invoke in shell.

    The args may contain None (will be discarded) or a list (will be flattened).

    Returns a list for the final commands.
    """
    caller = debug_utils.GetCallerName()

    def _CommandGenerator():
      if self._sudo:
        yield 'sudo'

      default_provider = self._provider_map.get('*', 'toybox')
      provider = self._provider_map.get(caller, default_provider)
      if provider:
        yield provider

      for arg in filter(None, args):
        if isinstance(arg, str):
          yield arg
        else:
          for sub_arg in arg:
            yield sub_arg

    # The command may be used several times (for both execution and printing
    # debug logs) so we do want to return a real list instead of generator.
    return list(_CommandGenerator())

  def base64(self, files=None, decode=False, ignore_non_alphabetic=False,
             wrap=76):
    """Encode or decode in base64.

    Args:
      files: A string or list of files to process.
      decode: True to decode, otherwise encode.
      ignore_non_alphabetic: True to ignore non-alphabetic characters.
      wrap: Wrap output at COLUMNS (default 76).
    """
    return self._device.CheckOutput(
        self._BuildCommand('base64',
                           '-d' if decode else None,
                           '-i' if ignore_non_alphabetic else None,
                           ['-w', str(wrap)],
                           files))

  def basename(self, path, suffix=None):
    """Return non-directory portion of a pathname removing suffix.

    Args:
      path: A pathname to retrieve base name.
      suffix: An optional suffix string to remove from path.
    """
    return self._device.CheckOutput(
        self._BuildCommand('basename',
                           path,
                           suffix)).strip()

  def blkid(self, *args, **kargs):
    raise NotImplementedError

  def blockdev(self, *args, **kargs):
    raise NotImplementedError

  def bzcat(self, *args, **kargs):
    raise NotImplementedError

  def cat(self, files, unbuffered=False):
    """Copy (concatenate) files to stdout.

    Args:
      unbuffered: True to copy one byte at a time (slow).

    Returns:
      Concatenated file contents.
    """
    return self._device.CheckOutput(
        self._BuildCommand('cat',
                           '-u' if unbuffered else None,
                           files))

  def chattr(self, *args, **kargs):
    raise NotImplementedError

  def chgrp(self, *args, **kargs):
    raise NotImplementedError

  def chmod(self, *args, **kargs):
    raise NotImplementedError

  def chown(self, *args, **kargs):
    raise NotImplementedError

  def chroot(self, *args, **kargs):
    raise NotImplementedError

  def chvt(self, number):
    """Change to virtual terminal number N. (This only works in text mode.)

    Virtual terminals are the Linux VGA text mode displays, ordinarily
    switched between via alt-F1, alt-F2, etc. Use ctrl-alt-F1 to switch
    from X to a virtual terminal, and alt-F6 (or F7, or F8) to get back.

    Args:
      number: An integer for virtual terminal number N.
    """
    self._device.CheckCall(self._BuildCommand('chvt', str(number)))

  def cksum(self, *args, **kargs):
    raise NotImplementedError

  def clear(self):
    """Clear the screen."""
    self._device.CheckCall(self._BuildCommand('clear'))

  def cmp(self, *args, **kargs):
    raise NotImplementedError

  def comm(self, *args, **kargs):
    raise NotImplementedError

  def count(self, *args, **kargs):
    raise NotImplementedError

  def cp(self, *args, **kargs):
    raise NotImplementedError

  def cpio(self, *args, **kargs):
    raise NotImplementedError

  def cut(self, *args, **kargs):
    raise NotImplementedError

  def date(self, *args, **kargs):
    raise NotImplementedError

  def dd(self, if_=None, of=None, ibs=None, obs=None, bs=None, count=None,
         skip=None, seek=None, conv=None):
    """Copy a file, converting and formatting according to the operands.

    Args:
      if_: Read from FILE instead of stdin.
      of: Write to FILE instead of stdout.
      bs: Read and write N bytes at a time.
      ibs: Read N bytes at a time.
      obs: Write N bytes at a time.
      count: Copy only N input blocks.
      skip: Skip N input blocks.
      seek: Skip N output blocks.
      conv: A list (or a string seperated by comma) from following args:
        notrunc: Don't truncate output file.
        noerror: Continue after read errors.
        sync: Pad blocks with zeros.
        fsync: Physically write data out before finishing.

    Returns:
      The output (from stdout) data.
    """
    valid_conv = ['notrunc', 'noerror', 'sync', 'fsync']
    if isinstance(conv, str):
      conv = conv.split(',')
    assert not conv or set(conv).issubset(valid_conv), (
        'dd using toybox does not support "conf=%s"')
    if conv:
      conv = ','.join(conv)
    return self._device.CheckOutput(self._BuildCommand(
        'dd',
        ['if=%s' % if_] if if_ else None,
        ['ibs=%s' % ibs] if ibs else None,
        ['of=%s' % of] if of else None,
        ['obs=%s' % obs] if obs else None,
        ['bs=%s' % bs] if bs else None,
        ['count=%s' % count] if count else None,
        ['skip=%s' % skip] if skip else None,
        ['seek=%s' % seek] if seek else None,
        ['conv=%s' % conv] if conv else None))

  def df(self, filesystems=None, fs_type=None):
    """The "disk free" command.

    The "disk free" command shows total/used/available disk space for each
    file system listed on the command line, or all currently mounted file
    systems.

    Args:
      filesystems: A string or list of file systems (mount points or dev file).
      fs_type: A string to display only filesystems of this type.

    Returns:
      A list of DISK_FREE_TUPLE objects representing the file system usage.
    """
    output = self._device.CheckOutput(self._BuildCommand(
        'df',
        ['-t', fs_type] if fs_type else None,
        filesystems)).splitlines()

    # Output example:
    # Filesystem      1K-blocks       Used  Available Use% Mounted on
    # udev             32924692         12   32924680   1% /dev
    if '1K-blocks' not in output[0]:
      raise IOError('df: Unknown output in header: %s' % output[0])

    def _output_filter(args):
      return [int(arg.strip('%')) if 0 < i < 5 else arg
              for i, arg in enumerate(args)]

    return [self.DISK_FREE_TUPLE(*_output_filter(line.split()))
            for line in output[1:]]

  def dirname(self, path):
    """Show directory portion of path."""
    return self._device.CheckOutput(self._BuildCommand('dirname', path)).strip()

  def dmesg(self, *args, **kargs):
    raise NotImplementedError

  def dos2unix(self, *args, **kargs):
    raise NotImplementedError

  def du(self, *args, **kargs):
    raise NotImplementedError

  def echo(self, *args, **kargs):
    raise NotImplementedError

  def egrep(self, *args, **kargs):
    raise NotImplementedError

  def eject(self, *args, **kargs):
    raise NotImplementedError

  def env(self, *args, **kargs):
    raise NotImplementedError

  def expand(self, *args, **kargs):
    raise NotImplementedError

  def fgrep(self, *args, **kargs):
    raise NotImplementedError

  def find(self, *args, **kargs):
    raise NotImplementedError

  def free(self, units='b'):
    """Returns total, free and used amount of physical memory and swap space.

    Args:
      units: Specify the output units (default is bytes).
          Available options: b, k, m, g, t.

    Returns:
      A MEM_FREE_TUPLE named tuple containing the memory information.
    """
    known_units = 'bkmgt'
    if units not in known_units:
      raise ValueError('free: invalid output unit <%s>' % units)

    raw_output = self._device.CheckOutput(self._BuildCommand(
        'free',
        '-%s' % units)).splitlines()

    # Output example:
    #           total        used        free      shared     buffers
    # Mem:      67450236928 62023270400  5426966528           0  2090393600
    # -/+ buffers/cache:    59932876800  7517360128
    # Swap:     68618809344  2034167808 66584641536
    mem = raw_output[1].split()[1:]
    cache = raw_output[2].split()[2:]
    swap = raw_output[3].split()[1:]
    return self.MEM_FREE_TUPLE(*list(map(int, mem + cache + swap)))

  def freeramdisk(self, *args, **kargs):
    raise NotImplementedError

  def fsfreeze(self, *args, **kargs):
    raise NotImplementedError

  def fstype(self, devices):
    """Returns a list of types of filesystem on a block device or image."""
    return self._device.CheckOutput(self._BuildCommand(
        'fstype',
        devices)).splitlines()

  def grep(self, *args, **kargs):
    raise NotImplementedError

  def groups(self, *args, **kargs):
    raise NotImplementedError

  def head(self, files, number=None):
    """Return first lines from files.

    Args:
      number: Number of lines to return.
      files: Files to read.
    """
    return self._device.CheckOutput(self._BuildCommand(
        'head',
        ('-n', str(number)) if number else None,
        files))

  def hostname(self, new_name=None):
    """Get/Set the current hostname.

    Args:
      new_name: An optional string to specify new host name.

    Returns:
      The (new) host name.
    """
    if new_name:
      self._device.CheckCall(self._BuildCommand('hostname', new_name))
      return new_name
    return self._device.CheckOutput(self._BuildCommand('hostname')).strip()

  def hwclock(self, *args, **kargs):
    raise NotImplementedError

  def id(self, *args, **kargs):
    raise NotImplementedError

  def ifconfig(self, *args, **kargs):
    raise NotImplementedError

  def inotifyd(self, *args, **kargs):
    raise NotImplementedError

  def install(self, *args, **kargs):
    raise NotImplementedError

  def ionice(self, *args, **kargs):
    raise NotImplementedError

  def iorenice(self, *args, **kargs):
    raise NotImplementedError

  def kill(self, *args, **kargs):
    raise NotImplementedError

  def killall(self, *args, **kargs):
    raise NotImplementedError

  def link(self, *args, **kargs):
    raise NotImplementedError

  def ln(self, *args, **kargs):
    raise NotImplementedError

  def logname(self):
    """Returns the current user name."""
    return self._device.CheckOutput(self._BuildCommand('logname')).strip()

  def losetup(self, *args, **kargs):
    raise NotImplementedError

  def ls(self, *args, **kargs):
    raise NotImplementedError

  def lsattr(self, *args, **kargs):
    raise NotImplementedError

  def lsmod(self, *args, **kargs):
    raise NotImplementedError

  def lspci(self, *args, **kargs):
    raise NotImplementedError

  def lsusb(self, *args, **kargs):
    raise NotImplementedError

  def makedevs(self, *args, **kargs):
    raise NotImplementedError

  def md5sum(self, *args, **kargs):
    raise NotImplementedError

  def mix(self, *args, **kargs):
    raise NotImplementedError

  def mkdir(self, *args, **kargs):
    raise NotImplementedError

  def mkfifo(self, *args, **kargs):
    raise NotImplementedError

  def mknod(self, *args, **kargs):
    raise NotImplementedError

  def mkswap(self, *args, **kargs):
    raise NotImplementedError

  def mktemp(self, *args, **kargs):
    raise NotImplementedError

  def modinfo(self, *args, **kargs):
    raise NotImplementedError

  def mount(self, device=None, mount_dir=None, options=None, fs_type=None,
            mount_all=False, fake_it=False, read_only=False, verbose=False):
    """Mount new filesystem(s) on directories.

    usage: mount [-afFrsvw] [-t TYPE] [-o OPTIONS...] [[DEVICE] DIR]

    With no arguments, display existing mounts.

    This mount autodetects loopback mounts (a file on a directory) and bind
    mounts (file on file, directory on directory), so you don't need to say
    --bind or --loop. You can also "mount -a /path" to mount everything in
    /etc/fstab under /path, even if it's noauto.

    Args:
      device: The device file to mount.
      mount_dir: The mount point for new file system.
      options: A list or comma separated string to specify mount options.
      fs_type: A string to specify filesystem type.
      mount_all: True to mount all entries in /etc/fstab (If fs_type is
          specified, only entries of that TYPE)
      fake_it: True to fake it ((don't actually mount).
      read_only: True to mount as read only (same as having 'ro' in options).
      verbose: True to get verbose output.

    Returns:
      A list of MOUNT_TUPLE for device mount information.
    """
    args = (options, fs_type, mount_all, fake_it, read_only, verbose)
    option_str = ''
    if options:
      if isinstance(options, str):
        option_str = options
      else:
        option_str = ','.join(options)
    arg_options = (['-o', option_str], ['-t', fs_type], '-a', '-f', '-r', '-v')

    raw_output = self._device.CheckOutput(self._BuildCommand(
        'mount',
        (option for i, option in enumerate(arg_options) if args[i]),
        device, mount_dir)).splitlines()

    # Example output:
    # rootfs on / type rootfs (rw)
    def mount_output_generator(line):
      value = line.split()
      return value[::2] + [value[-1].strip('()')]

    return [self.MOUNT_TUPLE(*mount_output_generator(line))
            for line in raw_output]

  def mountpoint(self, *args, **kargs):
    raise NotImplementedError

  def mv(self, *args, **kargs):
    raise NotImplementedError

  def nbd_client(self, *args, **kargs):
    raise NotImplementedError

  def nc(self, *args, **kargs):
    raise NotImplementedError

  def netcat(self, *args, **kargs):
    raise NotImplementedError

  def nice(self, *args, **kargs):
    raise NotImplementedError

  def nl(self, *args, **kargs):
    raise NotImplementedError

  def nohup(self, command):
    """Runs a command that survives the end of its terminal.

    Redirect tty on stdin to /dev/null, tty on stdout to "nohup.out".
    """
    self._device.CheckCall(self._BuildCommand(
        'nohup',
        command))

  def od(self, *args, **kargs):
    raise NotImplementedError

  def oneit(self, *args, **kargs):
    raise NotImplementedError

  def partprobe(self, devices):
    """Tell the kernel about partition table changes.

    Ask the kernel to re-read the partition table on the specified devices.

    Args:
      devices: A string or list for the devices to re-probe.
    """
    self._device.CheckCall(self._BuildCommand(
        'partprobe',
        devices))

  def paste(self, *args, **kargs):
    raise NotImplementedError

  def patch(self, *args, **kargs):
    raise NotImplementedError

  def pgrep(self):
    raise NotImplementedError

  def pidof(self, *args, **kargs):
    raise NotImplementedError

  def pivot_root(self, *args, **kargs):
    raise NotImplementedError

  def pkill(self, pattern, euid=None, exact=False, full=False, group=None,
            newest=False, oldest=False, parent=None, pgroup=None, session=None,
            signal=None, terminal=None, uid=None):
    """Signal processes based on its name and other attributes.

    Args:
      pattern: Extended regular expression for matching against the process
          names.
      euid: Match effective user ID. Either the numerical or symbolical value
          may be used.
      exact: True to match processes whose names (or command line if `full`
          is True) exactly match the pattern.
      full: True to check full command line for the pattern.
      group: Match real group ID. Either the numerical or symbolical value may
          be used.
      newest: Match only the newest process.
      oldest: Match only the oldest process.
      parent: Match parent process ID.
      pgroup: Match process group ID (0 for current).
      session: Match session ID (0 for current).
      signal: The signal to send to each matched process.
          Either the numeric or the symbolic signal name can be used.
      terminal: Match terminal name.
      uid: Match real user ID. Either the numerical or symbolical value may be
          used.
    """
    args = (euid, exact, full, group, newest, oldest, parent, pgroup, session,
            signal, terminal, uid, pattern)
    arg_options = (['-u', str(euid)], '-x', '-f', ['-G', str(group)], '-n',
                   '-o', ['-P', str(parent)], ['-g', str(pgroup)],
                   ['-s', str(session)], ['-l', str(signal)],
                   ['-t', str(terminal)], ['-U', uid], pipes.quote(pattern))

    return self._device.CheckCall(self._BuildCommand(
        'pkill',
        *(option for i, option in enumerate(arg_options)
          if args[i] is not None and args[i] is not False)))

  def pmap(self, *args, **kargs):
    raise NotImplementedError

  def printenv(self, *args, **kargs):
    raise NotImplementedError

  def printf(self, *args, **kargs):
    raise NotImplementedError

  def pwd(self, shell=None, absolute_path=None):
    """Print working (current) directory.

    Args:
      use_shell: Use shell's path from $PWD (when applicable)
      absolute_path: Print cannonical absolute path
    """
    return self._device.CheckOutput(self._BuildCommand(
        'pwd',
        '-L' if shell else None,
        '-P' if absolute_path else None)).strip()

  def readahead(self, *args, **kargs):
    raise NotImplementedError

  def readlink(self, *args, **kargs):
    raise NotImplementedError

  def realpath(self, *args, **kargs):
    raise NotImplementedError

  def renice(self, *args, **kargs):
    raise NotImplementedError

  def reset(self):
    """Reset the terminal."""
    self._device.CheckCall(self._BuildCommand('reset'))

  def rev(self, *args, **kargs):
    raise NotImplementedError

  def rfkill(self, *args, **kargs):
    raise NotImplementedError

  def rm(self, *args, **kargs):
    raise NotImplementedError

  def rmdir(self, dirnames, parents=False):
    """Remove one or more directories.

    Args:
      dirnames: A list of directories to remove.
      parents: Remove directory and its ancestors.
    """
    self._device.CheckCall(self._BuildCommand(
        'rmdir', '-p' if parents else None, dirnames))

  def sed(self, *args, **kargs):
    raise NotImplementedError

  def seq(self, *args, **kargs):
    raise NotImplementedError

  def setsid(self, *args, **kargs):
    raise NotImplementedError

  def sha1sum(self, *args, **kargs):
    raise NotImplementedError

  def shred(self, *args, **kargs):
    raise NotImplementedError

  def sleep(self, *args, **kargs):
    raise NotImplementedError

  def sort(self, *args, **kargs):
    raise NotImplementedError

  def split(self, *args, **kargs):
    raise NotImplementedError

  def stat(self, *args, **kargs):
    raise NotImplementedError

  def strings(self, *args, **kargs):
    raise NotImplementedError

  def switch_root(self, *args, **kargs):
    raise NotImplementedError

  def sync(self):
    """Write pending cached data to disk (synchronize), blocking until done."""
    self._device.CheckCall(self._BuildCommand('sync'))

  def sysctl(self, *args, **kargs):
    raise NotImplementedError

  def tac(self, *args, **kargs):
    raise NotImplementedError

  def tail(self, *args, **kargs):
    raise NotImplementedError

  def taskset(self, *args, **kargs):
    raise NotImplementedError

  def tee(self, *args, **kargs):
    raise NotImplementedError

  def time(self, *args, **kargs):
    raise NotImplementedError

  def timeout(self, *args, **kargs):
    raise NotImplementedError

  def touch(self, *args, **kargs):
    raise NotImplementedError

  def truncate(self, *args, **kargs):
    raise NotImplementedError

  def tty(self, *args, **kargs):
    raise NotImplementedError

  def umount(self, *args, **kargs):
    raise NotImplementedError

  def uname(self, *args, **kargs):
    raise NotImplementedError

  def uniq(self, *args, **kargs):
    raise NotImplementedError

  def unix2dos(self, *args, **kargs):
    raise NotImplementedError

  def unlink(self, path):
    """Deletes one file."""
    self._device.CheckCall(self._BuildCommand('unlink', path))

  def unshare(self, *args, **kargs):
    raise NotImplementedError

  def uptime(self):
    """Tell how long the system has been running and the system load.

    System load is reported by averages for the past 1, 5 and 15 minutes.

    Returns:
      A UPTIME_TUPLE named tuple for system load information.
    """
    raw_output = self._device.CheckOutput(self._BuildCommand('uptime'))

    # Output example:
    # 07:02:03 up 45 days,  4:56,  2 users,  load average: 1.26, 1.37, 1.20
    output = raw_output.split()
    return self.UPTIME_TUPLE(
        output[0], ' '.join(output[2:5]).strip(','),
        int(output[5]), float(output[9].strip(',')),
        float(output[10].strip(',')), float(output[11]))

  def usleep(self, *args, **kargs):
    raise NotImplementedError

  def uudecode(self, *args, **kargs):
    raise NotImplementedError

  def uuencode(self, *args, **kargs):
    raise NotImplementedError

  def vconfig(self, *args, **kargs):
    raise NotImplementedError

  def vmstat(self, *args, **kargs):
    raise NotImplementedError

  def w(self, *args, **kargs):
    raise NotImplementedError

  def wc(self, files, show_lines=None, show_words=None, show_bytes=None,
         show_chars=None):
    """Count lines, words, and characters in input.

    By default outputs lines, words, bytes, and filename for each
    argument (or from stdin if none). Displays only either bytes
    or characters.

    Args:
      show_lines: True to count by lines.
      show_words: True to count by words.
      show_bytes: True to count by bytes.
      show_chars: True to count by characters.

    Returns:
      A list of tuples providing count information. When there are multiple
      files one extra tuple wih file name "total" will be included as last item.
    """
    default_args = (True, True, True, False)
    args = (show_lines, show_words, show_bytes, show_chars)
    arg_options = ('-l', '-w', '-c', '-m')
    arg_names = ('lines', 'words', 'bytes', 'chars')

    # Normalize arguments.
    if not any(args):
      args = default_args

    raw_output = self._device.CheckOutput(self._BuildCommand(
        'wc',
        (option for i, option in enumerate(arg_options) if args[i]),
        files)).splitlines()

    # Build named tuple
    names = ' '.join(name for i, name in enumerate(arg_names) if args[i])
    wc_result = namedtuple('wc', names + ' filename')

    def _convert_numbers(args):
      return (int(var) if i + 1 < len(args) else var
              for i, var in enumerate(args))
    return [wc_result(*_convert_numbers(line.split())) for line in raw_output]

  def which(self, filenames, all_matches=False):
    """Search $PATH for executable files matching filename(s).

    Args:
      all_matches: True to show all matches.

    Returns:
      A list of matched files.
    """
    return self._device.CheckOutput(self._BuildCommand(
        'which',
        '-a' if all_matches else None,
        filenames)).splitlines()

  def who(self, *args, **kargs):
    raise NotImplementedError

  def whoami(self):
    """Returns the current user name."""
    return self._device.CheckOutput(self._BuildCommand('whoami')).strip()

  def xargs(self, *args, **kargs):
    raise NotImplementedError

  def xxd(self, *args, **kargs):
    raise NotImplementedError
