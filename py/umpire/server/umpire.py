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
import subprocess
import xmlrpclib

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import common
from cros.factory.umpire.server import config
from cros.factory.umpire.server import resource
from cros.factory.umpire.server import umpire_env
from cros.factory.utils.argparse_utils import CmdArg
from cros.factory.utils.argparse_utils import Command
from cros.factory.utils.argparse_utils import ParseCmdline
from cros.factory.utils.argparse_utils import verbosity_cmd_arg
from cros.factory.utils import debug_utils
from cros.factory.utils import file_utils


@Command('export-payload',
         CmdArg('bundle_id',
                help=('ID of the bundle that contains the payload resource '
                      'to export.')),
         CmdArg('payload_type',
                help=('Type name of the payload resource to export.')),
         CmdArg('file_path',
                help=('File path to export the specific resource.')))
def ExportPayload(args, umpire_cli):
  """Export a specific resource from a bundle

  It reads active config, download the specific resource of a bundle,
  and install it at the specified file_path.
  """
  print 'Exporting...'
  umpire_cli.ExportPayload(
      args.bundle_id, args.payload_type, os.path.realpath(args.file_path))
  print 'Export payload resource successfully.'


@Command('import-bundle',
         CmdArg(
             '--id',
             help=('the target bundle id. '
                   'If not specified, use "factory_bundle_YYYYMMDD_hhmmss".')),
         CmdArg('--note', help='a note for the bundle'),
         CmdArg('bundle_path', default='.',
                help='Bundle path. If not specified, use local path.'))
def ImportBundle(args, umpire_cli):
  """Imports a factory bundle to Umpire.

  It does the following: 1) copy bundle resources; 2) add a bundle item in
  bundles section in Umpire config; 3) prepend a ruleset for the new bundle;
  4) deploy the updated config.
  """
  message = 'Importing bundle %r' % args.bundle_path
  if args.id:
    message += ' with specified bundle ID %r' % args.id
  print message

  umpire_cli.ImportBundle(
      os.path.realpath(args.bundle_path), args.id, args.note)
  print 'Import bundle successfully.'


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


@Command('edit')
def Edit(args, umpire_cli):
  """Edits the Umpire config file.

  It calls editor (determined by environment variable VISUAL and EDITOR,
  defaults to vi) to edit the active config file and run deploy command with
  modified result afterward.
  """
  del args  # Unused.
  with file_utils.UnopenedTemporaryFile() as temp_path:
    file_utils.WriteFile(temp_path, umpire_cli.GetActiveConfig())
    # Use subprocess.call to avoid redirect stdin/stdout from terminal to pipe.
    # Most editors need stdin/stdout as terminal.
    ret = subprocess.call(
        os.getenv('VISUAL', os.getenv('EDITOR', 'vi')).split() + [temp_path])
    if ret == 0:
      _Deploy(temp_path, umpire_cli)
    else:
      raise common.UmpireError('Editor returned non-zero exit code %d' % ret)


@Command('deploy',
         CmdArg('config_path', help='Path of Umpire config file to deploy.'))
def Deploy(args, umpire_cli):
  """Deploys an Umpire service.

  It deploys the indicated config to Umpire service.
  """
  _Deploy(args.config_path, umpire_cli)


def _Deploy(config_path, umpire_cli):
  # First, ask Umpire daemon to validate config.
  print 'Validating config %r for deployment...' % config_path
  config_to_deploy = config.UmpireConfig(file_path=config_path)

  active_config = config.UmpireConfig(umpire_cli.GetActiveConfig())

  # Then, double confirm the user to deploy the config.
  print 'Changes for this deploy: '
  print '\n'.join(config.ShowDiff(active_config, config_to_deploy))
  if raw_input('Ok to deploy [y/n]? ') not in ['y', 'Y']:
    print 'Abort by user.'
    return

  # Deploying, finally.
  print 'Deploying config %r' % config_path
  umpire_cli.Deploy(
      umpire_cli.AddConfig(config_path, resource.ConfigTypeNames.umpire_config))
  print 'Deploy successfully.'


@Command('status')
def Status(args, umpire_cli):
  """Shows Umpire server status.

  Show active config content.
  """
  del args  # Unused.
  print 'Active config:'
  print umpire_cli.GetActiveConfig()


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
