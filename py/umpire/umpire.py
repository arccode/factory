#!/usr/bin/env python

# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire CLI (command line interface).

It parses command line arguments, packs them and makes JSON RPC call to
Umpire daemon (umpired). "init" command is an exception as umpired is not
running at that time.
"""

import logging
import os
import xmlrpclib

import factory_common  # pylint: disable=W0611
from cros.factory.common import SetupLogging
from cros.factory.hacked_argparse import (CmdArg, Command, ParseCmdline,
                                          verbosity_cmd_arg)
from cros.factory.umpire.commands import init
from cros.factory.umpire.commands import edit
from cros.factory.umpire import common
from cros.factory.umpire.config import ShowDiff
from cros.factory.umpire.umpire_env import UmpireEnv
from cros.factory.utils import file_utils


# Default Umpire base directory relative to root dir.
_DEFAULT_BASE_DIR = os.path.join('var', 'db', 'factory', 'umpire')


def UmpireCLI(env):
  """Gets connection to Umpire CLI XMLRPC server.

  Args:
    env: UmpireEnv object to get umpire_cli_port.

  Returns:
    A logical connection to an XML-RPC server
  """
  uri = 'http://127.0.0.1:%d' % env.umpire_cli_port
  logging.debug('UmpireCLI uri: %s', uri)
  return xmlrpclib.Server(uri)


@Command('init',
         CmdArg('--base-dir',
                help=('the Umpire base directory. If not specified, use '
                      '/var/db/factory/umpire/<board>')),
         CmdArg('--board',
                help=('board name the Umpire to serve. If not specified, use '
                      'board in bundle\'s MANIFEST.yaml')),
         CmdArg('--default', action='store_true',
                help='make umpire-<board> as default'),
         CmdArg('--local', action='store_true',
                help='do not set up /usr/local/bin and umpired'),
         CmdArg('--user', default='umpire',
                help='the user to run Umpire daemon'),
         CmdArg('--group', default='umpire',
                help='the group to run Umpire daemon'),
         CmdArg('bundle_path', default='.',
                help='Bundle path. If not specified, use local path.'))
def Init(args, env, root_dir='/'):
  """Initializes or updates an Umpire working environment.

  It creates base directory, installs Umpire executables and sets up daemon
  running environment. Base directory is specified by --base-dir or use
  /var/db/factory/umpire/<board>, where board is specified by --board or
  derived from bundle's MANIFEST.

  If an Umpire environment is already set, running it again will only update
  Umpire executables.

  Args:
    env: UmpireEnv object.
    root_dir: Root directory. Used for testing purpose.
  """
  def GetBoard():
    """Gets board name.

    It derives board name from bundle's MANIFEST.yaml.
    """
    manifest_path = os.path.join(args.bundle_path, common.BUNDLE_MANIFEST)
    manifest = common.LoadBundleManifest(manifest_path)
    try:
      return manifest['board']
    except:
      raise common.UmpireError(
          'Unable to resolve board name from bundle manifest: ' +
          manifest_path)

  board = args.board if args.board else GetBoard()

  # Sanity check: make sure factory toolkit exists.
  factory_toolkit_path = os.path.join(args.bundle_path,
                                      common.BUNDLE_FACTORY_TOOLKIT_PATH)
  file_utils.CheckPath(factory_toolkit_path, description='factory toolkit')

  base_dir = (args.base_dir if args.base_dir else
              os.path.join(root_dir, _DEFAULT_BASE_DIR, board))
  env.base_dir = base_dir

  init.Init(env, args.bundle_path, board, args.default, args.local, args.user,
            args.group)


@Command('import-bundle',
         CmdArg('--id',
                help=('the target bundle id. If not specified, use '
                      'bundle_name in bundle\'s MANIFEST.yaml')),
         CmdArg('bundle_path', default='.',
                help='Bundle path. If not specified, use local path.'))
def ImportBundle(args, env):
  """Imports a factory bundle to Umpire.

  It does the following: 1) sanity check for Umpire Config; 2) copy bundle
  resources; 3) add a bundle item in bundles section in Umpire Config;
  4) prepend a ruleset for the new bundle; 5) mark the updated config as
  staging and prompt user to edit it.
  """
  cli = UmpireCLI(env)
  cli.ImportBundle(os.path.realpath(args.bundle_path), args.id, args.note)


@Command('update',
         CmdArg('--from', dest='source_id',
                help=('the bundle id to update. If not specified, update the '
                      'last one in rulesets')),
         CmdArg('--to', dest='dest_id',
                help=('bundle id for the new updated bundle. If omitted, the '
                      'bundle is updated in place')),
         CmdArg('resources', nargs='+',
                help=('resource(s) to update. Format: '
                      '<resource_type>=/path/to/resource where resource_type '
                      'is one of ' + ', '.join(common.UPDATEABLE_RESOURCES))))
def Update(args, env):
  """Updates a specific resource of a bundle.

  It imports the specified resource(s) and updates the bundle's resource
  section. It can update the bundle in place, or copy the target bundle to a
  new one to update the resource.
  """
  cli = UmpireCLI(env)

  resources_to_update = []
  for resource in args.resources:
    resource_type, resource_path = resource.split('=', 1)
    if resource_type not in common.UPDATEABLE_RESOURCES:
      raise common.UmpireError('Unsupported resource type: ' + resource_type)
    if not os.path.isfile(resource_path):
      raise common.UmpireError('Resource file not found: ' + resource_path)
    resources_to_update.append((resource_type,
                                os.path.realpath(resource_path)))

  logging.debug('Invoke CLI Update(%r, source_id=%r,  dest_id=%r',
                resources_to_update, args.source_id, args.dest_id)
  cli.Update(resources_to_update, args.source_id, args.dest_id)

@Command('edit')
def Edit(args, env):
  """Edits the Umpire Config file.

  It calls user's default EDITOR to edit the config file and verifies the
  modified result afterward.
  """
  editor = edit.ConfigEditor(env, umpire_cli=UmpireCLI(env))
  editor.Edit(config_file=args.config)


@Command('deploy')
def Deploy(unused_args, env):
  """Deploys an Umpire service.

  It runs an Umpire service based on the staging Umpire Config (unless
  specified by --config).
  """
  # The config to deploy is already determined in _LoadConfig(). However,
  # we need to ask Umpire damnon to validate resources.
  config_path_to_deploy = os.path.realpath(env.config_path)
  if os.path.dirname(config_path_to_deploy) != env.resources_dir:
    raise common.UmpireError('Config to deploy %r must be in resources' %
                             env.config_path)

  # First, ask Umpire daemon to validate config.
  cli = UmpireCLI(env)
  cli.ValidateConfig(config_path_to_deploy)

  # Then, double confirm the user to deploy the config.
  ok_to_deploy = True
  if env.active_config_file:
    print 'Changes for this deploy: '
    print ''.join(ShowDiff(env.active_config_file, config_path_to_deploy))
    if raw_input('Ok to deploy [y/n]? ') not in ['y', 'Y']:
      ok_to_deploy = False

  # Deploying, finally.
  if ok_to_deploy:
    config_res = os.path.basename(config_path_to_deploy)
    cli.Deploy(config_res)


@Command('status')
def Status(unused_args, unused_env):
  """Shows the pstree of Umpire services."""
  raise NotImplementedError


@Command('list')
def List(unused_args, unused_env):
  """Lists all Umpire Config files."""


@Command('start')
def Start(unused_args, unused_env):
  """Starts Umpire service."""
  raise NotImplementedError


@Command('stop')
def Stop(unused_args, unused_env):
  """Stops Umpire service."""
  raise NotImplementedError


@Command('stage')
def Stage(unused_args, env):
  """Stages an Umpire Config file for edit."""
  env.StageConfigFile(env.config_path)


@Command('unstage')
def Unstage(unused_args, env):
  """Unstages staging Umpire Config file."""
  env.UnstageConfigFile()


@Command('import-resource',
         CmdArg('resources', nargs='+',
                help='Path to resource file(s).'))
def ImportResource(unused_args, unused_env):
  """Imports file(s) to resources folder."""
  raise NotImplementedError


def _LoadConfig(args, env):
  """Loads Umpire config file.

  It loads Umpire config file and stores in UmpireEnv object.

  Args:
    args: command line arguments
    env: UmpireEnv object

  Raises:
    UmpireError if config fails to load.
  """
  if args.command_name in ['import-bundle', 'update', 'stage']:
    # For import-bundle, update and stage command, it writes modified
    # config file and makes it staging. So no staging config should exist
    # when running the commands.
    if env.HasStagingConfigFile():
      raise common.UmpireError(
          'A staging config file exists. Please unstage it before '
          'import-bundle, update or stage.')
    env.LoadConfig(custom_path=args.config)
  elif args.command_name in ['start', 'stop']:
    env.LoadConfig(custom_path=args.config)
  elif args.command_name in ['edit', 'deploy']:
    env.LoadConfig(staging=True, custom_path=args.config)


def main():
  args = ParseCmdline(
      'Umpire CLI (command line interface)',
      CmdArg('--note', help='a note for this command'),
      CmdArg('--config', help='path to Umpire Config file'),
      verbosity_cmd_arg)
  SetupLogging(level=args.verbosity)
  env = UmpireEnv()
  _LoadConfig(args, env)
  args.command(args, env)


if __name__ == '__main__':
  main()
