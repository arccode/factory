#!/usr/bin/env python

# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire CLI (command line interface).

It parses command line arguments, packs them and makes JSON RPC call to
Umpire daemon (umpired). "init" command is an exception as umpired is not
running at that time.
"""


import factory_common  # pylint: disable=W0611
from cros.factory.common import SetupLogging
from cros.factory.hacked_argparse import (CmdArg, Command, ParseCmdline,
                                          verbosity_cmd_arg)
from cros.factory.umpire.common import UmpireEnv, UPDATEABLE_RESOURCES


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
                help='the group to run Umpire daemon'))
def Init(dummy_args, dummy_env):
  """Initializes or updates an Umpire working environment.

  It creates base directory, installs Umpire executables and sets up daemon
  running environment. Base directory is specified by --base-dir or use
  /var/db/factory/umpire/<board>, where board is specified by --board or
  derived from bundle's MANIFEST.

  If an Umpire environment is already set, running it again will only update
  Umpire executables.
  """
  raise NotImplementedError


@Command('import-bundle',
         CmdArg('--id',
                help=('the target bundle id. If not specified, use bundle_name '
                      'in bundle\'s MANIFEST.yaml')),
         CmdArg('bundle_path', default='.',
                help='Bundle path. If not specified, use local path.'))
def ImportBundle(dummy_args, dummy_env):
  """Imports a factory bundle to Umpire.

  It does the following: 1) sanity check for Umpire Config; 2) copy bundle
  resources; 3) add a bundle item in bundles section in Umpire Config;
  4) prepend a ruleset for the new bundle; 5) mark the updated config as
  staging and prompt user to edit it.
  """
  raise NotImplementedError


@Command('update',
         CmdArg('--from',
                help=('the bundle id to update. If not specified, update the '
                      'last one in rulesets')),
         CmdArg('--to',
                help=('bundle id for the new updated bundle. If omitted, the '
                      'bundle is updated in place')),
         CmdArg('resources', nargs='+',
                help=('resource(s) to update. Format: '
                      '<resource_type>=/path/to/resource where resource_type '
                      'is one of %s' % ', '.join(UPDATEABLE_RESOURCES))))
def Update(dummy_args, dummy_env):
  """Updates a specific resource of a bundle.

  It imports the specified resource(s) and updates the bundle's resource
  section. It can update the bundle in place, or copy the target bundle to a
  new one to update the resource.
  """
  raise NotImplementedError


@Command('edit')
def Edit(dummy_args, dummy_env):
  """Edits the Umpire Config file.

  It calls user's default EDITOR to edit the config file and verifies the
  modified result afterward.
  """
  raise NotImplementedError


@Command('deploy')
def Deploy(dummy_args, dummy_env):
  """Deploys an Umpire service.

  It runs an Umpire service based on the staging Umpire Config (unless specified
  by --config).
  """
  raise NotImplementedError


@Command('status')
def Status(dummy_args, dummy_env):
  """Shows the pstree of Umpire services."""
  raise NotImplementedError


@Command('list')
def List(dummy_args, dummy_env):
  """Lists all Umpire Config files."""


@Command('start')
def Start(dummy_args, dummy_env):
  """Starts Umpire service."""
  raise NotImplementedError


@Command('stop')
def Stop(dummy_args, dummy_env):
  """Stops Umpire service."""
  raise NotImplementedError


@Command('import-resource',
         CmdArg('resources', nargs='+',
                help='Path to resource file(s).'))
def ImportResource(dummy_args, dummy_env):
  """Imports file(s) to resources folder."""
  raise NotImplementedError


def main():
  args = ParseCmdline(
      'Umpire CLI (command line interface)',
      CmdArg('--note', help='a note for this command'),
      CmdArg('--config', help='path to Umpire Config file'),
      verbosity_cmd_arg)
  SetupLogging(level=args.verbosity)
  env = UmpireEnv()
  args.command(args, env)


if __name__ == '__main__':
  main()
