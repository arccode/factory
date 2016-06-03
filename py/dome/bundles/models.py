# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire bundle wrapper

We don't take advantage of django's database functionality because this system
should ideally be stateless. In other words, all information should be kept in
umpire instead of the database. This may not be possible for now, since umpire
config still lacks some critical information such as the history record.

TODO(littlecvr): make umpire config complete such that it contains all the
                 information we need.
"""

import os
import xmlrpclib

import yaml

# TODO(littlecvr): DRY
UMPIRE_BASE_DIR = os.path.join('/', 'var', 'db', 'factory', 'umpire')


class Bundle(object):
  """Provide functions to manipulate bundles in umpire.

  Umpire RPC calls aren't quite complete. For example, they do not provide any
  function to list bundles. So this class assumes that umpire runs on the same
  machine and is stored at its default location.

  TODO(littlecvr): complete the umpire RPC calls, decouple dome and umpire.
  """

  def __init__(self, name, note, file_path=None):
    self.name = name
    self.note = note

    self.file_path = file_path

    # TODO(littlecvr): add rulesets in umpire config.
    # TODO(littlecvr): add parts (toolkit, FSI, etc.)

  @staticmethod
  def _GetUmpireConfig(board):
    # TODO(littlecvr): DRY
    active_config_path = os.path.join(
        UMPIRE_BASE_DIR, board, 'active_umpire.yaml')
    with open(active_config_path) as f:
      return yaml.load(f.read())

  @staticmethod
  def ListAll(board):
    """Return all bundles as a list.

    This function returns all bundles as a list, no matter if the bundle is
    active or not. It is the front-end's responsibility to filter only bundles
    the user wants to see.

    Args:
      board: a string for name of the board.

    Return:
      A list of all bundles.
    """
    umpire_config = Bundle._GetUmpireConfig(board)

    bundle_list = []
    for b in umpire_config.get('bundles'):
      bundle_list.append(Bundle(b['id'], b.get('note')))

    return bundle_list

  @staticmethod
  def UploadNew(board, name, note, file_path):
    """Upload a new bundle.

    Args:
      board: the board name in string.
      name: name of the new bundle, in string. This corresponds to the "id"
          field in umpire config.
      note: commit message. This corresponds to the "note" field in umpire
          config.
      file_path: path to the bundle file. If the file is a temporary file, the
          caller is responsible for removing it.

    Return:
      The newly created bundle.
    """
    # create umpire RPC server object
    umpire_config = Bundle._GetUmpireConfig(board)
    # TODO(littlecvr): DRY
    port = umpire_config['port'] + 2  # cli port offset
    # TODO(littlecvr): DRY
    umpire_rpc_server = xmlrpclib.ServerProxy('http://localhost:%d' % port)

    # import bundle
    staging_config_path = umpire_rpc_server.ImportBundle(
        os.path.realpath(file_path), name, note)

    # make the bundle active
    with open(staging_config_path) as f:
      config = yaml.load(f.read())
    for ruleset in config['rulesets']:
      if ruleset['bundle_id'] == name:
        ruleset['active'] = True
        break
    with open(staging_config_path, 'w') as f:
      f.write(yaml.dump(config, default_flow_style=False))

    # validate and deploy
    umpire_status = umpire_rpc_server.GetStatus()
    config_to_deploy_text = umpire_status['staging_config']
    config_to_deploy_res = umpire_status['staging_config_res']
    umpire_rpc_server.ValidateConfig(config_to_deploy_text)
    umpire_rpc_server.Deploy(config_to_deploy_res)

    bundle_list = Bundle.ListAll(board)
    for b in bundle_list:
      if b.name == name:
        return b
    return None
