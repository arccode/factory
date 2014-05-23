# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common library of factory_flow module."""

import glob
import logging
import os

import factory_common   # pylint: disable=W0611
from cros.factory.hacked_argparse import CmdArg
from cros.factory.test import utils
from cros.factory.tools import build_board


# Arguments that are commonly used in commands.
board_cmd_arg = CmdArg('--board', help='board name to test')
bundle_dir_cmd_arg = CmdArg('--bundle', help='path to factory bundle directory')
dut_hostname_cmd_arg = CmdArg('--dut', help='IP or hostname of the DUT')

# Environmental variables for frequently used arguments. User can set these env
# vars to save the time typing the arguments each time.
BOARD_ENVVAR = 'FACTORY_FLOW_TESTING_BOARD'
DUT_ENVVAR = 'FACTORY_FLOW_TESTING_DUT'
BUNDLE_DIR_ENVVAR = 'FACTORY_FLOW_TESTING_BUNDLE_DIR'


def OnMoblab():
  """Checks if we are running on Moblab.

  Returns:
    True if runs on Moblab; False otherwise.
  """
  if (not utils.in_chroot() and
      build_board.BuildBoard().full_name == 'stumpy_moblab'):
    return True
  return False


class FactoryFlowError(Exception):
  """Factory flow error."""
  pass


class FactoryFlowCommand(object):
  """Base class for a factory_flow command.

  Properties:
    args: Arguments of the command.  Sub-class should overwrite this with their
      own arguments.
    options: The parsed options.
  """
  args = None
  options = None

  def _ParseBoard(self):
    """Parses board name if args has --board argument."""
    if board_cmd_arg in self.args:
      if self.options.board:
        self.options.board = build_board.BuildBoard(self.options.board)
      elif os.environ.get(BOARD_ENVVAR):
        self.options.board = build_board.BuildBoard(os.environ[BOARD_ENVVAR])
      else:
        # Use the value in src/scripts/.default_board.
        self.options.board = build_board.BuildBoard(None)

  def _ParseBundleDir(self):
    """Parses bundle directory path name if args has --bundle argument.

    Raises:
      ValueError if bundle dir cannot be resolved.
      FactoryFlowError if the given arg is not a valid bundle directory.
    """
    if bundle_dir_cmd_arg in self.args:
      if not self.options.bundle:
        if os.environ.get(BUNDLE_DIR_ENVVAR):
          self.options.bundle = os.environ[BUNDLE_DIR_ENVVAR]
        else:
          raise ValueError(
              'Unable to determine bundle directory; please specify with '
              '--bundle or set environment variable %r' % BUNDLE_DIR_ENVVAR)
      if not os.path.exists(os.path.join(self.options.bundle, 'MANIFEST.yaml')):
        bundle_glob = glob.glob(os.path.join(self.options.bundle,
                                             'factory_bundle_*'))
        if (len(bundle_glob) == 1 and
            os.path.exists(os.path.join(bundle_glob[0], 'MANIFEST.yaml'))):
          logging.info('Found bundle %r in %r', bundle_glob[0],
                       self.options.bundle)
          self.options.bundle = bundle_glob[0]
        else:
          raise FactoryFlowError('Directory %r is not a valid bundle directory',
                                 self.options.bundle)

  def _ParseDUTHostname(self):
    """Parses DUT hostname if args has --dut argument.

    Raises:
      ValueError if DUT hostname cannot be resolved.
    """
    if dut_hostname_cmd_arg in self.args:
      if self.options.dut:
        return
      elif os.environ.get(DUT_ENVVAR):
        self.options.dut = os.environ[DUT_ENVVAR]
      else:
        raise ValueError(
            'Unable to determine DUT hostname; please specify with --dut '
            'or set environment variable %r' % DUT_ENVVAR)

  def LocateUniquePath(self, file_type, globs):
    """Locates an unique full path name from the given globs.

    This method tries to find one and only one path name matched from the given
    globs.

    Args:
      file_type: The file type of the path; used in error messages.
      globs: A list of path specs to look for a path name match.

    Returns:
      The matched path name.

    Raises:
      FactoryFlowError if found no or more than one matched paths.
    """
    candidates = []
    for path_spec in globs:
      found_path = glob.glob(path_spec)
      candidates.extend(found_path)
    if not candidates:
      raise FactoryFlowError('Unable to locate %s' % file_type)
    if len(candidates) > 1:
      raise FactoryFlowError('Expect only one %s, but found: ' +
                             ', '.join(candidates))
    return candidates[0]

  def InitProperties(self):
    """Initializes instance properties."""
    self._ParseBoard()
    self._ParseBundleDir()
    self._ParseDUTHostname()

  def Main(self, options):
    """Main entry point of the command."""
    self.options = options
    try:
      self.InitProperties()
      self.Init()
      self.Run()
    finally:
      self.TearDown()

  def Init(self):
    """Optional init function."""
    pass

  def Run(self):
    """Runs the command."""
    raise NotImplementedError

  def TearDown(self):
    """Optional clean-up function."""
    pass
