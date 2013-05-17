# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Shopfloor resource importer.

This module provides helper function that imports factory bundle, generates
download configuration using a default template.
"""


import filecmp
import glob
import hashlib
import logging
import os
import shutil
import urllib
import yaml
from datetime import datetime

import factory_common  # pylint: disable=W0611
from cros.factory.shopfloor.launcher import constants, env, utils
from cros.factory.shopfloor.launcher import ShopFloorLauncherException


STATIC_FILES_PATTERN = 'factory_setup/static/*'
UPDATE_BUNDLE = 'shopfloor/shopfloor_data/update/factory.tar.bz2'
HWID_BUNDLE_PATTERN = 'hwid/hwid_*bundle*.sh'
FACTORY_SOFTWARE = 'shopfloor/factory.par'
NETBOOT_IMAGE = 'factory_shim/netboot/vmlinux.uimg'
SHOPFLOOR_TEMPLATE = 'shopfloor/shopfloor.template'


class ImporterError(Exception):
  pass


class BundleImporter(object):
  """Factory bundle importer.

  The importer parses and imports resources from a factory bundle directory.

  Example:
    from cros.factory.shopfloor.launcher import BundleImporter
    BundleImporter('path/to/factory/bundle').import()

  Properties:
    bundle:
      Full path name to factory bundle dir.
    datetime:
      The UTC date time of BundleImporter object been created.
    download_config:
      Base name of download config resource file.
    download_config_dict:
      A dictionary of downloadable resources for shopfloor.yaml.
    download_files:
      List of network download image tuples. The 2-tuple contains file full
      path name and its md5 hashsum.
    factory_software:
      factory.par file tuple.
    hwid_bundle:
      HWID updater file tuple.
    netboot_file:
      File tuple of netboot kernel vmlinux.uimg. Or None if it doesn't exist
      in this bundle dir.
    shopfloor_config:
      Generated shopfloor.yaml resource name.
    update_bundle:
      File tuple of factory.tar.bz2 update bundle.

  Args:
    bundle: factory bundle folder path.

  Raises:
    IOError: when bundle folder not found.
  """

  def __init__(self, bundle):
    self.bundle = os.path.abspath(bundle)

    if not os.path.isdir(bundle):
      raise IOError('Bundle dir not found')

    self.factory_software = self.GetFactorySoftware()
    if self.factory_software:
      logging.info(' - factory software: %s', self.factory_software)

    self.download_files = self.GetDownloadFiles()
    if self.download_files:
      logging.info(' - network download files:')
      map((lambda t: logging.info('    -  %s', t)),
          self.download_files)

    self.netboot_file = self.GetNetbootFile()
    if self.netboot_file:
      logging.info(' - netboot kernel: %s', self.netboot_file)

    self.update_bundle = self.GetUpdateBundle()
    if self.update_bundle:
      logging.info(' - update bundle: %s', self.update_bundle)

    self.hwid_bundle = self.GetHwidBundle()
    if self.hwid_bundle:
      logging.info(' - hwid bundle: %s', self.hwid_bundle)

    self.download_config = None
    self.download_config_dict = {}
    self.shopfloor_config = None
    self.datetime = datetime.utcnow()
    logging.info('UTC date time: %s', self.datetime)

  def GetFileTuple(self, file_name):
    """Gets (file_name, md5sum) tuple.

    Returns:
      (full path name, md5sum) tuple if file exists else None.

    Raises:
      IOError: if read failed.
    """
    if not os.path.isfile(file_name):
      return None
    return (file_name, utils.Md5sum(file_name))

  def GetFactorySoftware(self):
    """Gets factory.par file tuple."""
    return self.GetFileTuple(os.path.join(self.bundle, FACTORY_SOFTWARE))

  def GetDownloadFiles(self):
    """Gets downloadable partition file list."""
    files = glob.glob(os.path.join(self.bundle, STATIC_FILES_PATTERN))
    return [self.GetFileTuple(file_name) for file_name in files]

  def GetNetbootFile(self):
    """Gets netboot vmlinux.uimg path name."""
    return self.GetFileTuple(os.path.join(self.bundle, NETBOOT_IMAGE))

  def GetUpdateBundle(self):
    """Gets factory update bundle path name."""
    return self.GetFileTuple(os.path.join(self.bundle, UPDATE_BUNDLE))

  def GetHwidBundle(self):
    """Gets hwid update bundle path name.

    Raises:
      ImporterError: when more than 1 HWID bundles found.
    """
    hwid_bundles = glob.glob(os.path.join(self.bundle, HWID_BUNDLE_PATTERN))
    if not hwid_bundles:
      return None
    if len(hwid_bundles) > 1:
      raise ImporterError('More than one HWID bundles found.')
    return self.GetFileTuple(hwid_bundles[0])

  def GetResourceName(self, file_tuple):
    """Converts (path_name, md5sum) tuple to resource name."""
    return '#'.join([os.path.basename(file_tuple[0]), file_tuple[1][0:8]])

  def ReadShopfloorTemplate(self):
    """Reads shopfloor.template YAML file from bundle directory.

    Raises:
      IOError: when read from template failed.
      ImporterError: when no template found in bundle and install dir.
    """
    template = os.path.join(self.bundle, SHOPFLOOR_TEMPLATE)
    if not os.path.isfile(template):
      template = os.path.join(constants.SHOPFLOOR_INSTALL_DIR, 'shopfloor.yaml')
      if not os.path.isfile(template):
        raise ImporterError('Can not find shopfloor YAML config template.')

    return yaml.load(open(template, 'r'))

  def Import(self):
    """Imports resources.

    This function converts downloadble images, netboot kernel image, factory
    update bundle to resources. Download configuration default.conf#[md5sum]
    and shopfloor configuration shopfloor.yaml#[md5sum] will be generated.

    Raises:
      IOError: when disk full or copy failed.
      ImporterError: when resources name conflict.
    """

    # File tuple list generated from bundle (src_file, md5sum).
    bundle_files = []
    bundle_files.extend(self.download_files)
    bundle_files.extend([self.netboot_file, self.update_bundle,
                        self.hwid_bundle, self.factory_software])
    bundle_files = filter(None, bundle_files)

    # File-resource tuple list (src_file, res_file).
    copy_list = []
    # Hash conflict tuble list (src_file, src_md5, dest_file, dest_md5).
    conflict_list = []
    # Unexpected error list of tuple (src_file, res_base_name, str(e)).
    error_list = []
    # Validate source files and destination resources
    for file_tuple in bundle_files:
      f, md5sum = file_tuple
      res_base_name = self.GetResourceName(file_tuple)
      dest_file = os.path.join(env.GetResourcesDir(), res_base_name)
      if os.path.isfile(dest_file):
        try:
          utils.VerifyResource(dest_file)
          logging.info(' - resource exists, skip: %s', dest_file)
        except ShopFloorLauncherException:
          copy_list.append(f, dest_file)
        except Exception, e:
          error_list.append((f, res_base_name, str(e)))
        else:
          # Do not trust os.state(), perform a non-shallow file compare.
          if not filecmp.cmp(f, dest_file, shallow=False):
            # 32bit hash conflict
            conflict_list.append(
                (f, md5sum, dest_file, utils.Md5sum(dest_file)))
      else:
        copy_list.append((f, dest_file))

    # Raise exception on hash conflict
    if conflict_list:
      for src, src_hash, dst, dst_hash in conflict_list:
        logging.warning('hash conflict:\n\t%s:%s\n\t%s:%s',
                      src_hash, src, dst_hash, dst)
      raise ImporterError('Hash conflicted')
    # Raise exception on unexpected error
    if error_list:
      for src, res, err in error_list:
        logging.error('error:\n\t%s / %s\n\t%s',
                      src, res, err)
      raise ImporterError('Unexpected error')
    # Copy resources
    logging.info('importing resources ...')
    map((lambda t: shutil.copy2(t[0], t[1])), copy_list)
    logging.info('    done')

    # Generate download configuration and shopfloor.yaml
    self.WriteDownloadConfig()
    self.WriteShopfloorConfig()

  def GetChannel(self, base_name):
    """Converts file base name to download channel."""
    if base_name == 'rootfs-release':
      channel = 'release'
    elif base_name == 'rootfs-test':
      channel = 'factory'
    else:
      channel = base_name
    return channel.upper()

  def WriteDownloadConfig(self):
    """Generate download config and writes to resource folder.

    Raises:
      IOError: when write failed.
    """
    if not self.download_files:
      return

    config = []
    # Also prepare a dictionary based config for shopfloor.yaml .
    # sf_config holds a partial shopfloor.yaml dict that indicates
    # resources under:
    # <root>
    #   |--network_install
    #   |    |--board
    #   |    |    |--default    # <== sf_config here
    #   |    |    |    |--default
    #   |    |    |    |    |--config: default.conf#
    #   |    |    |    |    |--oem: oem.gz#
    #   .    .    .    .    .
    sf_config = {}

    config.append('# date:   %s' % self.datetime)
    config.append('# bundle: %s' % self.bundle)
    for file_tuple in self.download_files:
      f = file_tuple[0]
      base_name = os.path.basename(f)
      # Skip non-gzipped file and remove '.gz' from file name.
      if not base_name.endswith('.gz'):
        continue
      base_name = base_name[:-3]
      res_name = self.GetResourceName(file_tuple)
      url_name = urllib.quote(res_name)
      sha1sum = utils.B64Sha1(f)
      channel = self.GetChannel(base_name)
      config.append(':'.join([channel, url_name, sha1sum]))
      sf_config[base_name] = res_name

    default_conf = '\n'.join(config)
    conf_md5 = hashlib.md5(default_conf).hexdigest()  # pylint: disable=E1101
    sf_config['config'] = self.GetResourceName(('default.conf', conf_md5))
    self.download_config = os.path.join(env.GetResourcesDir(),
                                        sf_config['config'])

    open(self.download_config, 'w').write(default_conf)
    self.download_config_dict = sf_config

  def WriteShopfloorConfig(self):
    """Generates shopfloor.yaml from the factory bundle."""
    config = self.ReadShopfloorTemplate()
    # TODO(rongchang): import info from bundle MANIFEST.yaml
    config['info']['version'] = os.path.basename(self.bundle)
    config['info']['note'] = str(self.datetime)
    # Patch download configuration
    if self.download_config_dict:
      config['network_install']['board']['default'] = self.download_config_dict
    # Patch netboot kernel resource
    if self.netboot_file:
      config['network_install']['netboot_kernel'] = (
          self.GetResourceName(self.netboot_file))
    # Patch update bundle and HWID bundle
    if 'updater' not in config:
      config['updater'] = {}
    if self.update_bundle:
      config['updater']['update_bundle'] = self.GetResourceName(
          self.update_bundle)
    if self.hwid_bundle:
      config['updater']['hwid_bundle'] = self.GetResourceName(self.hwid_bundle)
    # Patch factory software resource
    if self.factory_software:
      config['shopfloor']['factory_software'] = (
          self.GetResourceName(self.factory_software))

    yaml_text = yaml.dump(config, default_flow_style=False)
    yaml_md5 = hashlib.md5(yaml_text).hexdigest() # pylint: disable=E1101

    self.shopfloor_config = os.path.join(
        env.GetResourcesDir(),
        self.GetResourceName(('shopfloor.yaml', yaml_md5)))

    open(self.shopfloor_config, 'w').write(yaml_text)
    logging.info('Shopfloor import from bundle complete.\n\n\tNew config: %s\n',
                 os.path.basename(self.shopfloor_config))

