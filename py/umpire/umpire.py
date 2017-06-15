#!/usr/bin/env python

# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire CLI (command line interface).

It parses command line arguments, packs them and makes JSON RPC call to
Umpire daemon (umpired).
"""

import logging
import os
import xmlrpclib

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.commands import edit
from cros.factory.umpire import common
from cros.factory.umpire import config
from cros.factory.umpire import resource
from cros.factory.umpire import umpire_env
from cros.factory.utils.argparse_utils import CmdArg
from cros.factory.utils.argparse_utils import Command
from cros.factory.utils.argparse_utils import ParseCmdline
from cros.factory.utils.argparse_utils import verbosity_cmd_arg
from cros.factory.utils import debug_utils
from cros.factory.utils import file_utils


@Command('import-bundle',
         CmdArg('--id',
                help=('the target bundle id. If not specified, use '
                      'bundle_name in bundle\'s MANIFEST.yaml')),
         CmdArg('--note', help='a note for the bundle'),
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
  print 'Import bundle successfully. Staging config %r' % staging_config_path


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
                      'is one of ' + ', '.join(resource.PayloadTypeNames))))
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
  for item in args.resources:
    resource_type, resource_path = item.split('=', 1)
    if resource_type not in resource.PayloadTypeNames:
      raise common.UmpireError('Unsupported resource type: ' + resource_type)
    file_utils.CheckPath(resource_path, 'resource')
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
  with edit.ConfigEditor(umpire_cli, max_retry=3) as editor:
    editor.Edit(config_file=args.config)


@Command('deploy')
def Deploy(args, umpire_cli):
  """Deploys an Umpire service.

  It deploys current staging config to Umpire service.
  If users want to run a specific config, stage it first.
  """
  del args  # Unused.
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
  config_to_deploy = config.UmpireConfig(config_to_deploy_text,
                                         validate=False)
  active_config = config.UmpireConfig(active_config_text,
                                      validate=False)
  print '\n'.join(config.ShowDiff(active_config, config_to_deploy))
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
def Status(args, umpire_cli):
  """Shows Umpire server status.

  Shows staging config status.
  In verbose mode, show active config content and diff it with staging.
  """
  status = umpire_cli.GetStatus()
  if not status:
    raise common.UmpireError('Unable to get status from Umpire server')

  if args.verbose:
    print 'Active config (%s):' % status['active_config_res']
    print status['active_config']
    print

  if status['staging_config']:
    print 'Staging config exists (%s)' % status['staging_config_res']
    if args.verbose:
      active_config = config.UmpireConfig(status['active_config'])
      staging_config = config.UmpireConfig(status['staging_config'])
      print 'Diff between active and staging config:'
      print '\n'.join(config.ShowDiff(active_config, staging_config))
  else:
    print 'No staging config'


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
def Unstage(args, umpire_cli):
  """Unstages staging Umpire config file."""
  del args  # Unused.
  print 'Unstage config %r successfully.' % umpire_cli.UnstageConfigFile()


@Command('start-service',
         CmdArg('services',
                help='Comma separate list of services to start.'))
def StartService(args, umpire_cli):
  """Starts a list of Umpire services."""
  services = args.services.split(',')
  umpire_cli.StartServices(services)


@Command('stop-service',
         CmdArg('services',
                help='Comma separate list of services to stop.'))
def StopService(args, umpire_cli):
  """Stops a list of Umpire services."""
  services = args.services.split(',')
  umpire_cli.StopServices(services)


def _UmpireCLI():
  """Gets XMLRPC server proxy to Umpire CLI server.

  Server port is obtained from active Umpire config.

  Returns:
    Umpire CLI XMLRPC server proxy
  """
  env = umpire_env.UmpireEnv()
  env.LoadConfig(validate=False)

  umpire_cli_uri = 'http://127.0.0.1:%d' % env.umpire_cli_port
  logging.debug('Umpire CLI server URI: %s', umpire_cli_uri)
  server_proxy = xmlrpclib.ServerProxy(umpire_cli_uri, allow_none=True)
  return server_proxy


def main():
  args = ParseCmdline(
      'Umpire CLI (command line interface)',
      verbosity_cmd_arg)
  debug_utils.SetupLogging(level=args.verbosity)

  try:
    umpire_cli = _UmpireCLI()
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
