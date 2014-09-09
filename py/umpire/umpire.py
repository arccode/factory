#!/usr/bin/env python

# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire CLI (command line interface).

It parses command line arguments, packs them and makes JSON RPC call to
Umpire daemon (umpired). "init" command is an exception as umpired is not
running at that time.
"""

import errno
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
from cros.factory.umpire import config as umpire_config
from cros.factory.umpire.umpire_env import UmpireEnv
from cros.factory.utils import file_utils
from cros.factory.utils import process_utils


@Command('init',
         CmdArg('--base-dir',
                help=('the Umpire base directory. If not specified, use '
                      '%s/<board>' % common.DEFAULT_BASE_DIR)),
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
def Init(args, root_dir='/'):
  """Initializes or updates an Umpire working environment.

  It creates base directory, installs Umpire executables and sets up daemon
  running environment. Base directory is specified by --base-dir or use
  common.DEFAULT_BASE_DIR/<board>, where board is specified by --board or
  derived from bundle's MANIFEST.

  If an Umpire environment is already set, running it again will only update
  Umpire executables.

  Args:
    args: Command line args.
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

  # This is an empty UmpireEnv object with base directory.
  env = UmpireEnv()
  env.base_dir = (args.base_dir if args.base_dir else
                  os.path.join(root_dir, common.DEFAULT_BASE_DIR, board))

  init.Init(env, args.bundle_path, board, args.default, args.local, args.user,
            args.group)


@Command('import-bundle',
         CmdArg('--id',
                help=('the target bundle id. If not specified, use '
                      'bundle_name in bundle\'s MANIFEST.yaml')),
         CmdArg('bundle_path', default='.',
                help='Bundle path. If not specified, use local path.'))
def ImportBundle(args, umpire_cli):
  """Imports a factory bundle to Umpire.

  It does the following: 1) sanity check for Umpire config; 2) copy bundle
  resources; 3) add a bundle item in bundles section in Umpire config;
  4) prepend a ruleset for the new bundle; 5) mark the updated config as
  staging and prompt user to edit it.
  """
  message = 'Importing bundle %r' % args.bundle_path
  if args.id:
    message += ' with specified bundle ID %r' % args.id
  print message

  staging_config_path = umpire_cli.ImportBundle(
      os.path.realpath(args.bundle_path), args.id, args.note)
  print 'Import bundle successfully. Staging config %r' % (
      staging_config_path)


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
def Update(args, umpire_cli):
  """Updates a specific resource of a bundle.

  It imports the specified resource(s) and updates the bundle's resource
  section. It can update the bundle in place, or copy the target bundle to a
  new one to update the resource.
  """
  resources_to_update = []
  source_bundle = ('bundle %r' % args.source_id if args.source_id
                   else 'default bundle')
  if not args.dest_id:
    print 'Updating resources of %s in place' % source_bundle
  else:
    print 'Creating a new bundle %r based on %s with new resources' % (
        args.dest_id, source_bundle)

  print 'Updating resources:'
  for resource in args.resources:
    resource_type, resource_path = resource.split('=', 1)
    if resource_type not in common.UPDATEABLE_RESOURCES:
      raise common.UmpireError('Unsupported resource type: ' + resource_type)
    if not os.path.isfile(resource_path):
      raise IOError(errno.ENOENT, 'Resource file not found', resource_path)
    resource_real_path = os.path.realpath(resource_path)
    print '  %s  %s' % (resource_type, resource_real_path)
    resources_to_update.append((resource_type, resource_real_path))

  logging.debug('Invoke CLI Update(%r, source_id=%r,  dest_id=%r)',
                resources_to_update, args.source_id, args.dest_id)
  umpire_cli.Update(resources_to_update, args.source_id, args.dest_id)
  print 'Update successfully.'


@Command('edit',
         CmdArg('--config',
                help=('Path to Umpire config file to edit. Default uses '
                      'current staging config. If there is no staging config, '
                      'stage the active config.')))
def Edit(args, umpire_cli):
  """Edits the Umpire config file.

  It calls user's default EDITOR to edit the config file and verifies the
  modified result afterward.
  """
  editor = edit.ConfigEditor(umpire_cli, max_retry=3)
  editor.Edit(config_file=args.config)


@Command('deploy')
def Deploy(unused_args, umpire_cli):
  """Deploys an Umpire service.

  It deploys current staging config to Umpire service.
  If users want to run a specific config, staging it first.
  """
  print 'Getting status...'
  umpire_status = umpire_cli.GetStatus()
  if not umpire_status['staging_config']:
    raise common.UmpireError('Unable to deploy as there is no staging file')
  config_to_deploy_text = umpire_status['staging_config']
  config_to_deploy_res = umpire_status['staging_config_res']

  # First, ask Umpire daemon to validate config.
  print 'Validating staging config for deployment...'
  umpire_cli.ValidateConfig(config_to_deploy_text)

  # Then, double confirm the user to deploy the config.
  print 'Changes for this deploy: '
  active_config_text = umpire_status['active_config']
  config_to_deploy = umpire_config.UmpireConfig(config_to_deploy_text,
                                                validate=False)
  active_config = umpire_config.UmpireConfig(active_config_text,
                                             validate=False)
  print ''.join(umpire_config.ShowDiff(active_config, config_to_deploy))
  if raw_input('Ok to deploy [y/n]? ') not in ['y', 'Y']:
    print 'Abort by user.'
    return

  # Deploying, finally.
  print 'Deploying config %r' % config_to_deploy_res
  umpire_cli.Deploy(config_to_deploy_res)
  print 'Deploy successfully.'


@Command('status',
         CmdArg('--verbose', action='store_true',
                help='Show detailed status.'))
def Status(args, umpire_cli, board):
  """Shows Umpire server status.

  Shows Umpire daemon running status, staging config status.
  In verbose mode, show active config content and diff it with statging.
  """
  if not board:
    raise common.UmpireError('Unable to get board from active config')
  umpired_status = process_utils.CheckOutput(
      ['initctl', 'status', 'umpire', 'BOARD=%s' % board])
  print 'Umpire dameon status: ', umpired_status

  status = umpire_cli.GetStatus()
  if not status:
    raise common.UmpireError('Unable to get status from Umpire server')

  if status['board'] != board:
    raise common.UmpireError(
        'Board name from Umpire server %r is different from board name from '
        'local Umpire CLI %r' % (status['board'], board))

  if args.verbose:
    print 'Active config (%s):' % status['active_config_res']
    print status['active_config']
    print

  if status['staging_config']:
    print 'Staging config exists (%s)' % status['staging_config_res']
    if args.verbose:
      active_config = umpire_config.UmpireConfig(status['active_config'])
      staging_config = umpire_config.UmpireConfig(status['staging_config'])
      print 'Diff between active and staging config:'
      print ''.join(umpire_config.ShowDiff(active_config, staging_config))
  else:
    print 'No staging config'

  print 'Mapping of bundle_id => shop floor handler path:'
  # Because XMLRPC converts tuple to list, so convert it back as string
  # formatting expects tuple.
  print '\n'.join('  %s => %s' % tuple(m) for m in status['shop_floor_mapping'])
  print


@Command('list')
def List(unused_args, unused_umpire_cli):
  """Lists all Umpire config files."""
  raise NotImplementedError


@Command('start')
def Start(unused_args, unused_umpire_cli):
  """Starts Umpire service."""
  raise NotImplementedError


@Command('stop')
def Stop(unused_args, umpire_cli):
  """Stops Umpire service."""
  umpire_cli.StopUmpired()


@Command('stage',
         CmdArg('--config',
                help=('Path to Umpire config file. Default uses current active '
                      'config.')))
def Stage(args, umpire_cli):
  """Stages an Umpire config file for edit."""
  if args.config:
    umpire_cli.StageConfigFile(args.config)
    print 'Stage config %s successfully.' % args.config
  else:
    print (
        'ERROR: For "umpire stage", --config must be specified. '
        'If you want to edit active config. Just run "umpire edit" '
        'and it stages active config for you to edit.')


@Command('unstage')
def Unstage(unused_args, umpire_cli):
  """Unstages staging Umpire config file."""
  print 'Unstage config %r successfully.' % umpire_cli.UnstageConfigFile()


@Command('import-resource',
         CmdArg('resources', nargs='+',
                help='Path to resource file(s).'))
def ImportResource(args, umpire_cli):
  """Imports file(s) to resources folder."""
  # Find out absolute path of resources and perform simple sanity check.
  for path in args.resources:
    resource_path = os.path.abspath(path)
    if not os.path.isfile(resource_path):
      raise IOError(errno.ENOENT, 'Resource file not found', resource_path)

    print 'Adding %r to resources' % resource_path
    resource_name = umpire_cli.AddResource(resource_path)
    print 'Resource added as %r' %  resource_name


def _UmpireCLI():
  """Gets XMLRPC server proxy to Umpire CLI server.

  Server port is obtained from active Umpire config.

  Returns:
    (Umpire CLI XMLRPC server proxy, UmpireEnv object)
  """
  env = UmpireEnv()
  env.LoadConfig(init_shop_floor_manager=False, validate=False)

  umpire_cli_uri = 'http://127.0.0.1:%d' % env.umpire_cli_port
  logging.debug('Umpire CLI server URI: %s', umpire_cli_uri)
  server_proxy = xmlrpclib.ServerProxy(umpire_cli_uri, allow_none=True)
  return (server_proxy, env)


def main():
  args = ParseCmdline(
      'Umpire CLI (command line interface)',
      CmdArg('--note', help='a note for this command'),
      verbosity_cmd_arg)
  SetupLogging(level=args.verbosity)

  if args.command_name == 'init':
    args.command(args)
  else:
    try:
      (umpire_cli, env) = _UmpireCLI()
      if args.command_name == 'status':
        args.command(args, umpire_cli, env.config.get('board'))
      else:
        args.command(args, umpire_cli)
    except xmlrpclib.Fault as e:
      if e.faultCode == xmlrpclib.APPLICATION_ERROR:
        print ('ERROR: Problem running %s due to umpired application error. '
               'Server traceback:\n%s' % (args.command_name, e.faultString))
      else:
        print 'ERROR: Problem running %s due to XMLRPC Fault: %s' % (
            args.command_name, e)
    except Exception as e:
      print 'ERROR: Problem running %s. Exception %s' % (args.command_name, e)


if __name__ == '__main__':
  main()
