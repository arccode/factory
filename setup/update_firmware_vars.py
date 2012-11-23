#!/usr/bin/env python
#
# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Update environment variables in a legacy_image.bin."""

import copy
import optparse
import os
import shutil
import struct
import subprocess
import sys
import zlib


# Some environment variables are "first class"--you can set them with simple
# command line options.  Those are listed here with the mapping for how to
# change the command-line option into an environment variable.
OPTION_ENVIRONMENT_VARS = {
  'tftpserverip': 'tftpserverip=%s',
}

# Some kernel arguments are also "first class".  They are listed here.
OPTION_KERNEL_ARGS = {
  'omahaserver': 'omahaserver=%s',
  'board': 'cros_board=%s',
}

# This is the environment we'll write, which tells to merge this environment
# with whatever is stored in u-boot as the "default" environment.
DEFAULT_ENV = (
  "merge_with_default=1\0"
)

# Format of the CRC in the output file.
CRC_FORMAT = '<i'


class ArgumentError(Exception):
  """We'll raise this whenever we have an error that was caused by user-error.

  This could be a bad argument or the inability to access a file on the
  filesystem.
  """
  pass


class _OptionWithMemsize(optparse.Option):
  """Option subclass that has an additional 'memsize' option.

  The memsize option allows you to add a k/m/g suffix to your integers to
  specify KiB, MiB, or GiB.


  >>> parser = optparse.OptionParser(option_class=_OptionWithMemsize)
  >>> _ = parser.add_option('--test', type='memsize')

  # Simple: just a number of bytes...
  >>> opts, args = parser.parse_args(['--test', '999'])
  >>> print opts
  {'test': 999}

  # Can do hex number of bytes...
  >>> opts, args = parser.parse_args(['--test', '0x1000'])
  >>> print opts
  {'test': 4096}

  # Kilobyte suffix...
  >>> opts, args = parser.parse_args(['--test', '1k'])
  >>> print opts
  {'test': 1024}

  # Can handle hex and upper-case suffix too..
  >>> opts, args = parser.parse_args(['--test', '0xfK'])
  >>> print opts
  {'test': 15360}

  # Check other suffixes
  >>> opts, args = parser.parse_args(['--test', '1m'])
  >>> print opts
  {'test': 1048576}
  >>> opts, args = parser.parse_args(['--test', '1g'])
  >>> print opts
  {'test': 1073741824}

  # Negative test cases; need to quiet stderr first...
  >>> import StringIO
  >>> _oldstderr = sys.stderr
  >>> sys.stderr = StringIO.StringIO()
  >>> opts, args = parser.parse_args(['--test', 'hello'])
  Traceback (most recent call last):
      ...
  SystemExit: 2
  >>> opts, args = parser.parse_args(['--test', ''])
  Traceback (most recent call last):
      ...
  SystemExit: 2
  >>> sys.stderr = _oldstderr
  """

  @staticmethod
  def _CheckMemsize(option, opt, value):
    """Check that a 'memsize' option to optparse is good.

    Args:
      option: See optparse manual.
      opt: Option name we're parsing; See optparse manual.
      value: Value we're parsing; See optparse manual.
    Returns:
      value: The parsed value.
    Raises:
      OptionValueError: Upon error
    """
    # Note: purposely no 'b' suffix, since that makes 0x12b ambiguous.
    multiplier_table = [
      ('g', 1024 * 1024 * 1024),
      ('m', 1024 * 1024),
      ('k', 1024),
      ('', 1),
    ]
    for (suffix, multiplier) in multiplier_table:
      if value.lower().endswith(suffix):
        new_value = value
        if suffix:
          new_value = new_value[:-len(suffix)]
        try:
          # Convert w/ base 0 (handles hex, binary, octal, etc)
          return int(new_value, 0) * multiplier
        except ValueError:
          # Pass and try other suffixes; not useful now, but may be useful
          # later if we ever allow B vs. GB vs. GiB.
          pass
    raise optparse.OptionValueError("option %s: invalid memsize value: %r" %
                                    (opt, value))

  TYPES = optparse.Option.TYPES + ('memsize',)
  TYPE_CHECKER = copy.copy(optparse.Option.TYPE_CHECKER)
_OptionWithMemsize.TYPE_CHECKER['memsize'] = _OptionWithMemsize._CheckMemsize


def _GetSpecialEnvVars(opts):
  """Grab env vars that the user can set directly via command-line options.

  >>> class FakeOpts(object): pass
  >>> opts = FakeOpts()
  >>> opts.tftpserverip = None

  >>> _GetSpecialEnvVars(opts)
  []

  >>> opts.tftpserverip = "1.2.3.4"
  >>> sorted(_GetSpecialEnvVars(opts))
  ['tftpserverip=1.2.3.4']

  Args:
    opts: The options from the option parser.

  Returns:
    vars: A list of 'key=value' strings for u-boot environment variables.
  """
  vars = []
  for opt_name, value in OPTION_ENVIRONMENT_VARS.iteritems():
    if getattr(opts, opt_name):
      vars.append(OPTION_ENVIRONMENT_VARS[opt_name] % getattr(opts, opt_name))
  return vars


def _GetSpecialKernelArgs(opts):
  """Grab kernel args that the user can set directly via command-line options.

  >>> class FakeOpts(object): pass
  >>> opts = FakeOpts()
  >>> opts.omahaserver = None
  >>> opts.board = None

  >>> _GetSpecialKernelArgs(opts)
  []

  >>> opts.omahaserver = "3.4.5.6"
  >>> sorted(_GetSpecialKernelArgs(opts))
  ['omahaserver=3.4.5.6']

  >>> opts.board = "tegra2_kaen-gobi"
  >>> sorted(_GetSpecialKernelArgs(opts))
  ['cros_board=tegra2_kaen-gobi', 'omahaserver=3.4.5.6']

  Args:
    opts: The options from the option parser.

  Returns:
    vars: A list of strings that will eventually be joined with space to create
      the kernel command line.
  """
  vars = []
  for opt_name, value in OPTION_KERNEL_ARGS.iteritems():
    if getattr(opts, opt_name):
      vars.append(OPTION_KERNEL_ARGS[opt_name] % getattr(opts, opt_name))
  return vars


def _BuildEnvironment(env_vars, kernel_args, env_size):
  """Build up the u-boot environment string.

  >>> s = _BuildEnvironment(['a=b', 'c=d'], ['noinitrd', 'x=y'], 0x100)
  >>> len(s)
  256

  >>> _ParseEnvStr(s)
  ['merge_with_default=1', 'a=b', 'c=d', 'extra_bootargs=noinitrd x=y']

  Args:
    env_vars: List of env_vars to put in the environment (after the default).
    env_size: Final size of the environment.

  Returns:
    env_str: The environment string for u-boot, including checksum.
  """
  assert DEFAULT_ENV.endswith('\0')

  # Add the command-line args in through extra_bootargs
  if kernel_args:
    env_vars += ['extra_bootargs=%s' % (' '.join(kernel_args))]

  env_str = DEFAULT_ENV + '\0'.join(env_vars)

  # Pad to full size...
  padding_bytes = env_size - struct.calcsize(CRC_FORMAT) - len(env_str)
  if padding_bytes < 0:
    raise ArgumentError("Environment %d bytes too big" % -padding_bytes)
  env_str += '\0' * padding_bytes

  # Add in the CRC.
  crc = zlib.crc32(env_str)
  crc_str = struct.pack(CRC_FORMAT, crc)

  return crc_str + env_str


def _ParseEnvStr(env_str):
  """Read an environment string and return variables in it.

  # Test corrupt case; valid case is tested by _BuildEnvironment()
  >>> _ParseEnvStr('hello; this is not valid') is None
  True

  Args:
    env_str: The string to read

  Returns:
    env_vars: The variables in the string, or None if the CRC was bad.
  """
  crc_bytes = struct.calcsize(CRC_FORMAT)

  stored_crc, = struct.unpack(CRC_FORMAT, env_str[:crc_bytes])
  env_str = env_str[crc_bytes:]
  calc_crc = zlib.crc32(env_str)

  if stored_crc != calc_crc:
    return None

  return env_str.rstrip('\0').split('\0')


def _MakeOutput(input_path, output_path, fw_size):
  """Make and open the output file.

  Handles copying the input file to the output file (if the user desires that)
  and also padding.

  # Doctests; for tests below...
  #   file 1: 0x1000 of zeros
  #   file 2: should be a copy of file 1
  #   file 3: 0x1000 of 0xff, eventually padded to 0x2000 with 0s.
  #   file 4: copy of file 3 padded to 0x2000 with 0s.
  >>> import tempfile
  >>> work_dir = tempfile.mkdtemp('doctest')
  >>> path1 = os.path.join(work_dir, '1.bin')
  >>> path2 = os.path.join(work_dir, '2.bin')
  >>> path3 = os.path.join(work_dir, '3.bin')
  >>> path4 = os.path.join(work_dir, '4.bin')
  >>> open(path1, 'wb').write(chr(0) * 0x1000)
  >>> open(path3, 'wb').write(chr(0xff) * 0x1000)

  # Try making a copy: from 1 to 2
  >>> s = _MakeOutput(path1, path2, 0x1000).read()
  >>> len(s) == 0x1000
  True
  >>> s == chr(0) * 0x1000
  True

  # No-op (just opens file); tell it to pad the size it already is.
  >>> s = _MakeOutput(path1, None, 0x1000).read()
  >>> len(s) == 0x1000
  True
  >>> s == chr(0) * 0x1000
  True

  # Try padding w/ a copy
  >>> s = _MakeOutput(path3, path4, 0x2000).read()
  >>> len(s) == 0x2000
  True
  >>> s == (chr(0xff) * 0x1000) + (chr(0) * 0x1000)
  True

  # Try padding w/out a copy
  >>> s = _MakeOutput(path3, None, 0x2000).read()
  >>> len(s) == 0x2000
  True
  >>> s == (chr(0xff) * 0x1000) + (chr(0) * 0x1000)
  True

  # Double-check sizes
  >>> os.path.getsize(path1) == 0x1000
  True
  >>> os.path.getsize(path2) == 0x1000
  True
  >>> os.path.getsize(path3) == 0x2000
  True
  >>> os.path.getsize(path4) == 0x2000
  True


  Args:
    input_path: Path the the input firmware file.
    output_path: Path to the output firmware file; if None/blank we'll modify
        the input in place.
    fw_size: If non-None, we'll pad to this many bytes.

  Returns:
    outfile: The output file.  Already contains the input and has been padded.
        Left seeked at 0.
  """
  if not output_path:
    output_path = input_path
  else:
    output_dir = os.path.dirname(output_path)
    if not os.path.isdir(output_dir):
      raise ArgumentError("The destination directory %s doesn't exist" %
                          output_dir)

    try:
      shutil.copy(input_path, output_path)
    except IOError, e:
      raise ArgumentError("Problem copying input to output: %s" % str(e))

  try:
    outfile = open(output_path, 'r+b')
  except IOError, e:
    raise ArgumentError("Problem opening output file: %s" % str(e))

  if fw_size:
    old_size = os.path.getsize(output_path)
    if fw_size < old_size:
      raise ArgumentError("Can't specify firmware size smaller than input")

    padding_bytes = fw_size - old_size
    if padding_bytes:
      outfile.seek(0, os.SEEK_END)
      outfile.write('\0' * padding_bytes)
      outfile.seek(0)

  return outfile


def _GetEnvVarAddr(image_file):
  """Get environment variable section address from FMAP.

  Args:
    image_file: The image file to look for environment variable section.

  Returns:
    The address of RW_ENVIRONMENT section is returned.
  """
  try:
    command = ["dump_fmap", "-p", image_file.name, "RW_ENVIRONMENT"]
    stream = subprocess.Popen(command, stdout=subprocess.PIPE)
    result = stream.communicate()[0].split()
    if len(result) == 0:
      raise ArgumentError("Cannot find RW_ENVIRONMENT section in FMAP.")
    addr = int(result[1])
    return addr
  except OSError:
    raise ArgumentError("Error calling dump_fmap.")


def _PutEnvInFile(outfile, env_str, clobber_ok):
  """Put the given environment into the output file.

  At the moment, this just crams the env_str to the end of the file.

  # Sample call with a fake (all zero) file.
  >>> import StringIO
  >>> FILE_SIZE=0x10000
  >>> f = StringIO.StringIO(chr(0) * FILE_SIZE)
  >>> env_str = _BuildEnvironment([], [], 0x100)
  >>> _PutEnvInFile(f, env_str, False)
  >>> s = f.getvalue()

  # File should have kept the same size.
  >>> len(s) == FILE_SIZE
  True

  # File should end with env_str and start with '\0'
  >>> s[:-0x100].strip(chr(0))
  ''
  >>> s[-0x100:] == env_str
  True

  # Running again should get an error if clobbering not OK.
  >>> _PutEnvInFile(f, env_str, False)
  Traceback (most recent call last):
      ...
  ArgumentError: Old arguments will be clobbered; pass --force if OK

  # Should be OK if clobbering OK
  >>> _PutEnvInFile(f, env_str, True)
  >>> s_new = f.getvalue()
  >>> s == s_new
  True

  Args:
    outfile: An already opened file.
    env_str: The str to store.
    clobber_ok: If True, it's OK to clobber the old environment; if False we'll
        raise an exception if we detect and old environment.
  """
  env_size = len(env_str)
  addr = _GetEnvVarAddr(outfile)
  outfile.seek(addr, os.SEEK_SET)

  old_env_str = outfile.read(env_size)
  if old_env_str != ('\0' * env_size):
    old_env = _ParseEnvStr(old_env_str)

    # If we get here, our old env section was neither zeros nor valid.
    # that probably means that we either had an unpadded firmware image as
    # input or a completely bogus input file.
    if old_env is None:
      raise ArgumentError("Previous vars were not zero nor valid")

    if not clobber_ok:
      raise ArgumentError("Old arguments will be clobbered; pass --force if OK")

  outfile.seek(addr, os.SEEK_SET)
  outfile.write(env_str)


def _ParseOptions():
  """Parse command-line arguments.

  Returns:
    opts: Options from optparse.OptionParser.
  """
  parser = optparse.OptionParser(description=__doc__,
                                 option_class=_OptionWithMemsize)

  parser.add_option('--env-size', dest='env_size', default=0x1000,
                    type='memsize',
                    help='If specified, overrides the default env_size that '
                    'u-boot expects')
  parser.add_option('--fw-size', dest='fw_size', default=None, type='memsize',
                    help='If specified, firmware will be padded to be this '
                    'many bytes')
  parser.add_option('--input', '-i', dest='input', default=None,
                    help='Path to the firmware to modify; required')
  parser.add_option('--output', '-o', dest='output', default=None,
                    help='Path to store output; if not specified we will '
                    'directly modify the input file')
  parser.add_option('--force', '-f', dest='force', default=False,
                    action='store_true',
                    help='Bypass ignorable errors')

  # Special-case options to make things simpler for factory.  Must match
  # OPTION_ENVIRONMENT_VARS and OPTION_KERNEL_ARGS
  parser.add_option('--tftpserverip', default=None,
                    help='Set the TFTP server IP address')

  parser.add_option('--board', default=None,
                    help='Set the cros_board to be passed into the kernel')
  parser.add_option('--omahaserver', default=None,
                    help='Set the Omaha server IP address')

  parser.add_option('--var', default=[], dest='vars', metavar='var',
                    action='append',
                    help='Set any arbitrary u-boot var using format arg=value')
  parser.add_option('--arg', default=[], dest='args', metavar='arg',
                    action='append',
                    help='Set any arbitrary kernel command line arg')

  opts, args = parser.parse_args()
  if args:
    raise ArgumentError('Unexpected argument(s): %s' % ', '.join(args))

  if not opts.input:
    raise ArgumentError("You must specify the input image")

  return opts


def main():
  """Main function."""
  prog_name = os.path.basename(sys.argv[0])

  try:
    opts = _ParseOptions()
    try:
      print 'Input:  %s (0x%08x bytes)' % (opts.input,
                                           os.path.getsize(opts.input))
    except OSError:
      raise ArgumentError("Error accessing input image: %s" % opts.input)

    env_vars = opts.vars + _GetSpecialEnvVars(opts)
    kernel_args = opts.args + _GetSpecialKernelArgs(opts)
    env_str = _BuildEnvironment(env_vars, kernel_args, opts.env_size)
    outfile = _MakeOutput(opts.input, opts.output, opts.fw_size)
    _PutEnvInFile(outfile, env_str, opts.force)

    print 'Output: %s (0x%08x bytes)' % (outfile.name,
                                         os.path.getsize(outfile.name))
    print '\n  '.join(['Stored env:'] + env_vars)
  except ArgumentError, e:
    print >>sys.stderr, "%s: error: %s" % (prog_name, str(e))
    sys.exit(1)


def _Test(verbose=''):
  """Run any built-in tests."""
  import doctest
  assert verbose in ('', '-v')
  doctest.testmod(verbose=(verbose == '-v'))


if __name__ == '__main__':
  if sys.argv[1:2] == ["--test"]:
    _Test(*sys.argv[2:])
  else:
    main()
