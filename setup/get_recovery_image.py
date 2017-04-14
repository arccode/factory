#!/usr/bin/python

# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(hungte) The 'release only' mode is actually broken after cros_payload
# system is introduced. We may revise or remove this module in future.

""" Script for auto fetching the latest stable images on-line
and setup the environment for miniomaha server.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import urllib
import zipfile

class BoardNotFoundException(Exception):
  pass

class OmahaPreparer(object):
  """Class for preparing all the necessary files for mini-omaha server."""
  conf_filename = 'miniomaha.conf'

  def __init__(self, script_dir, cache_dir, config_path=None):
    self.script_dir = script_dir
    self.cache_dir = cache_dir
    self.boards_to_update = None
    self.version_offset = None
    self.omaha_config_path = config_path

  def set_boards_to_update(self, _boards_to_update):
    self.boards_to_update = _boards_to_update

  def set_version_offset(self, _version_offset):
    self.version_offset = _version_offset

  def _read_config(self, config_path):
    output = {}
    with open(config_path, 'r') as f:
      exec(f.read(), output)
    return output['config']

  def generate_files_from_image(self, board_name):
    """Generate all the files and config with respect to a new image."""
    # create data directory if necessary
    data_dir = os.path.join(self.cache_dir, board_name)
    if os.path.exists(data_dir):
      shutil.rmtree(data_dir)
    os.makedirs(data_dir)

    # unzip the image of the target board
    for cached_file in os.listdir(self.cache_dir):
      if '%s_' % board_name in cached_file:
        zip_file = zipfile.ZipFile(os.path.join(self.cache_dir, cached_file))
        zip_file.extractall(data_dir)
        zip_file.close()

    # find the unzipped image
    file_path = glob.glob(os.path.join(data_dir, '*.bin'))[0]

    # call make_factory_package.sh, the result is stored in data_dir
    return_value = subprocess.call(
        [os.path.join(self.script_dir, 'make_factory_package.sh'),
         '--board=%s' % board_name,
         '--release=%s' % file_path,
         '--test=none',
         '--toolkit=none',
         '--hwid=none',
         '--omaha_data_dir=%s' % data_dir])
    if return_value:
      sys.exit("Failed to run make_factory_package.sh")
    os.remove(file_path)

    # read and delete the temporary config file
    config_path = os.path.join(data_dir, self.conf_filename)
    config = self._read_config(config_path)
    os.remove(config_path)

    # modify fields into the miniomaha readable form
    new_config = {}
    if config:
      new_config = config[0]
      for keys in new_config:
        if keys.endswith('_image'):
          dir_name = board_name
          if self.version_offset:
            dir_name = os.path.join(self.version_offset, board_name)
          new_config[keys] = os.path.join(dir_name, new_config[keys])

    return new_config

  def generate_miniomaha_files(self):
    """Generate files for the updated boards."""
    config_path = os.path.join(self.cache_dir, self.conf_filename)
    if os.path.exists(config_path):
      factory_configs = self._read_config(config_path)
    else:
      factory_configs = []

    # remove the old information of updated boards from config
    for board in self.boards_to_update:
      factory_configs[:] = [config for config in factory_configs
          if board not in config['qual_ids']]

    # generate the new configs and file for updated boards
    for board in self.boards_to_update:
      config = self.generate_files_from_image(board)
      if not config:
        sys.exit("Failed to generate config files")
      factory_configs.append(config)

    with open(config_path, 'w') as f:
      f.write('config=%s\n' % factory_configs)

  def setup_miniomaha_files(self):
    """Move the updated files to mini-omaha static directory."""
    omaha_dir = os.path.join(self.script_dir, 'static')
    if self.version_offset:
      omaha_dir = os.path.join(omaha_dir, self.version_offset)
    if not os.path.isdir(omaha_dir):
      os.makedirs(omaha_dir)
    for board in self.boards_to_update:
      target_dir = os.path.join(omaha_dir, board)
      if os.path.isdir(target_dir):
        shutil.rmtree(target_dir)
      os.rename(os.path.join(self.cache_dir, board), target_dir)
    omaha_config_path = (self.omaha_config_path or
                         os.path.join(omaha_dir, self.conf_filename))
    shutil.copy(os.path.join(self.cache_dir, self.conf_filename),
                omaha_config_path)


class ImageUpdater(object):
  """Class for requesting the latest stable image from server."""
  conf_url = 'https://dl.google.com/dl/edgedl/chromeos/recovery/recovery.conf'

  def __init__(self):
    self.board_images = []

  def _get_version_info(self):
    """Download and analyze the version information from server."""
    urllib.urlretrieve(self.conf_url, 'recovery.conf')

    with open('recovery.conf', 'r') as f:
      current_version = '0.0.0.0'
      for line in f:
        stanza = line.strip().split('=')
        if stanza[0] == 'url':
          if (current_version, stanza[1]) not in self.board_images:
            self.board_images.append((current_version, stanza[1]))
        elif stanza[0] == 'version':
          current_version = stanza[1]

  def update_image(self, board_name, cache_dir):
    """Check and update an image of the give board name."""
    self._get_version_info()
    update_filename = ''
    update_url = ''
    for version, url in self.board_images:
      if '%s_' % board_name in url:
        update_filename = '%s_%s.bin.zip' % (board_name, version)
        update_url = url
        break

    if not update_filename:
      raise BoardNotFoundException

    need_update = True
    for cached_file in os.listdir(cache_dir):
      if '%s_' % board_name in cached_file:
        if cached_file == update_filename:
          need_update = False
        else:
          os.remove(os.path.join(cache_dir, cached_file))
        break

    if need_update:
      urllib.urlretrieve(update_url, os.path.join(cache_dir, update_filename))

    return need_update


def main():
  base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
  usage = 'usage: %prog [options]'
  parser = argparse.ArgumentParser(
    description=usage,
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('--board', dest='boards', nargs='+',
                      help='board name for downloading the new stable image')
  parser.add_argument('--cache', dest='cache_dir', default=None,
                      help='cache directory for downloaded images')
  parser.add_argument('--restart', action='store_true',
                      dest='restart', default=False,
                      help='run make_factory_package for all assigned boards')

  options = parser.parse_args()
  boards = options.boards
  if not boards:
    sys.exit('At least a board must be assigned')
  cache_dir = (options.cache_dir or
               os.path.realpath(os.path.join(base_path, 'cache_dir')))

  if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)

  updater = ImageUpdater()
  boards_to_update = []
  # TODO(chunyen): add an option to download all images in the config file.
  for board in list(boards):
    updated = None
    try:
      updated = updater.update_image(board, cache_dir)
    except BoardNotFoundException:
      print 'WARNING: No board named %s is found, ignored' % board
      boards.remove(board)
    if updated:
      boards_to_update.append(board)
  if options.restart:
    boards_to_update = boards
  omaha_preparer = OmahaPreparer(base_path, cache_dir)
  omaha_preparer.set_boards_to_update(boards_to_update)
  omaha_preparer.generate_miniomaha_files()
  omaha_preparer.setup_miniomaha_files()


if __name__ == '__main__':
  main()
