# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common library of factory_flow module."""

import glob
import logging
import os
import sys
import yaml

import factory_common   # pylint: disable=W0611
from cros.factory.umpire import common as umpire_common
from cros.factory.utils.argparse_utils import CmdArg
from cros.factory.utils import cros_board_utils
from cros.factory.utils import file_utils


# Arguments that are commonly used in commands.
board_cmd_arg = CmdArg('--board', help='board name to test')
bundle_dir_cmd_arg = CmdArg('--bundle', help='path to factory bundle directory')
dut_hostname_cmd_arg = CmdArg('--dut', help='IP or hostname of the DUT')
project_cmd_arg = CmdArg('--project', type=str, default=None,
                         help='project name to test, default to board name')

# Environmental variables for frequently used arguments. User can set these env
# vars to save the time typing the arguments each time.
BOARD_ENVVAR = 'FACTORY_FLOW_TESTING_BOARD'
DUT_ENVVAR = 'FACTORY_FLOW_TESTING_DUT'
BUNDLE_DIR_ENVVAR = 'FACTORY_FLOW_TESTING_BUNDLE_DIR'


def GetFactoryParPath():
  """Gets the path to the factory.par executable.

  Returns:
    The path to the factory.par executable, extracted from sys.path, if the
    module is invoked through the factory.par; None otherwise.
  """
  # Check if path to factory.par is in sys.path.
  par_file = [p for p in sys.path if p.endswith('factory.par')]
  if not par_file:
    return None
  return par_file[0]


def GetEnclosingFactoryBundle():
  """Checks if we are running using factory.par inside a factory bundle.

  In a standard factory bundle the factory.par for factory flow tools is at

    <factory bundle dir>/factory_flow/factory.par

  This function checks if path to factory.par is in sys.path and if
  MANIFEST.yaml exists in upper-level directory of factory.par to determine if
  we are running factory.par inside a factory bundle.

  Returns:
    Base factory bundle path if runs with factory.par inside a factory bundle;
    None otherwise.
  """
  par_file_path = GetFactoryParPath()
  if not par_file_path:
    return None
  # Check if MANIFEST.yaml exists one level above the directory where
  # factory.par sits.
  bundle_dir = os.path.dirname(os.path.dirname(par_file_path))
  if os.path.exists(os.path.join(bundle_dir, 'MANIFEST.yaml')):
    return bundle_dir
  return None


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
      par_bundle_dir = GetEnclosingFactoryBundle()
      if self.options.board:
        self.options.board = cros_board_utils.BuildBoard(self.options.board)
      elif os.environ.get(BOARD_ENVVAR):
        self.options.board = cros_board_utils.BuildBoard(
            os.environ[BOARD_ENVVAR])
      elif par_bundle_dir:
        self.options.board = cros_board_utils.BuildBoard(
            umpire_common.LoadBundleManifest(
                os.path.join(par_bundle_dir, 'MANIFEST.yaml'))['board'])
      else:
        # Use the value in src/scripts/.default_board.
        self.options.board = cros_board_utils.BuildBoard(None)

  def _ParseBundleDir(self):
    """Parses bundle directory path name if args has --bundle argument.

    Raises:
      ValueError if bundle dir cannot be resolved.
      FactoryFlowError if the given arg is not a valid bundle directory.
    """
    if bundle_dir_cmd_arg in self.args:
      if not self.options.bundle:
        par_bundle_dir = GetEnclosingFactoryBundle()
        if os.environ.get(BUNDLE_DIR_ENVVAR):
          self.options.bundle = os.environ[BUNDLE_DIR_ENVVAR]
        elif par_bundle_dir:
          self.options.bundle = par_bundle_dir
        else:
          raise ValueError(
              'Unable to determine bundle directory; please specify with '
              '--bundle or set environment variable %r' % BUNDLE_DIR_ENVVAR)
      # Verify if the bundle directory is valid.
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

  def _ParseProjectName(self):
    """Parses the project name if args has --project argument.

    Raises:
      ValueError if the default project name cannot be resolved.
    """
    if project_cmd_arg not in self.args:
      return
    if self.options.project is None:
      if not hasattr(self.options, 'board'):
        raise ValueError(
            'Unable to determine the default project name; please explicitly '
            'specify the project name with --project or specify the default '
            'project name with %s' % board_cmd_arg[0])
      self.options.project = self.options.board.short_name

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
    self._ParseProjectName()

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
    raise FactoryFlowError('Failed to load MANIFEST.yaml: ' + str(e))
