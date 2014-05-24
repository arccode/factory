# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# pylint: disable=E1101

"""Common Umpire RPC Commands."""

import glob
import logging
import os
import time
from twisted.web import xmlrpc
import xmlrpclib

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.bundle_selector import SelectRuleset
from cros.factory.umpire.common import ParseResourceName, UmpireError
from cros.factory.umpire.umpire_rpc import RPCCall, UmpireRPC
from cros.factory.umpire.utils import Deprecate


VERSION_COMPONENTS = ['firmware_bios', 'firmware_ec', 'hwid', 'rootfs_test',
                      'rootfs_release']
HASH_COMPONENTS = ['device_factory_toolkit']
ALL_COMPONENTS = VERSION_COMPONENTS + HASH_COMPONENTS
# Factory stages in running sequence.
FACTORY_STAGES = ['SMT', 'RUNIN', 'FA', 'GRT']
SYNC_URL = '%{scheme}s://%{ip}s:%{port}d/%{path}s/%{toolkit_md5sum}s/'


def Fault(message, reason=xmlrpclib.INVALID_METHOD_PARAMS):
  """Instanciates an XMLRPC Fault() object.

  xmlrpc.Fault() notifies the RPC client that remote function was terminated
  incorrectly.
  """
  return xmlrpc.Fault(reason, UmpireError(message))



class RootDUTCommands(UmpireRPC):

  """Root DUT (Device Under Test) remote procedures.

  Root commands for v1 and v2 compatiblilities.

  RPC URL:
    http://umpire_server_address:umpire_port/RPC2
  """

  @RPCCall
  def Ping(self):
    return {'version': self.env.umpire_version_major}


class UmpireDUTCommands(UmpireRPC):

  """Umpire DUT remote procedures.

  RPC URL:
    http://umpire_server_address:umpire_port/umpire
  """

  @RPCCall
  def GetTime(self):
    return time.time()

  @RPCCall
  @Deprecate
  def ListParameters(self, pattern):
    """Lists files that match the pattern in parameters directory.

     Args:
       pattern: A pattern string for glob to list matched files.

     Returns:
       A list of matched files.

     Raises:
       ValueError if caller is trying to query outside parameters directory.
    """
    parameters_dir = os.path.join(self.env.base_dir, 'parameters')
    glob_pathname = os.path.abspath(os.path.join(parameters_dir, pattern))
    if not glob_pathname.startswith(parameters_dir):
      raise ValueError('ListParameters is limited to parameter directory')

    matched_file = glob.glob(glob_pathname)
    # Only return files.
    matched_file = filter(os.path.isfile, matched_file)
    return [os.path.relpath(x, self.parameters_dir) for x in matched_file]

  @RPCCall
  @Deprecate
  def GetParameter(self, path):
    """Gets the assigned parameter file.

     Args:
       path: A relative path for locating the parameter.

     Returns:
       Content of the parameter. It is always wrapped in a shopfloor.Binary
       object to provides best flexibility.

     Raises:
       ValueError if the parameter does not exist or is not under
       parameters folder.
    """
    parameters_dir = os.path.join(self.env.base_dir, 'parameters')
    abspath = os.path.abspath(os.path.join(parameters_dir, path))
    if not abspath.startswith(parameters_dir):
      raise ValueError('GetParameter is limited to parameter directory')

    if not os.path.isfile(abspath):
      raise ValueError('File does not exist or it is not a file')

    return xmlrpc.Binary(open(abspath).read())

  @staticmethod
  def _GetResourceTag(component, resource_filename):
    """Gets resource tag and resource hash tuple from name.

    Tag can be version or hex MD5SUM value depends on component name is in
    VERSION_COMPONENTS or HASH_COMPONENTS.

    Args:
      component: resource type.
      resource_filename: resource file name.

    Returns:
      (resource_tag, resource_hash) tuple. Where resource_tag can be version
      string or resource MD5SUM hexstring depends on component in VERSION_ or
      HASH_ list.
    """
    _, resource_version, resource_hash = ParseResourceName(resource_filename)
    if component in HASH_COMPONENTS:
      return (resource_hash, resource_hash)
    else:
      if component.startswith('firmware_'):
        (ec_version, bios_version) = resource_version.split(':')
        if component.endswith('_ec'):
          return (ec_version, resource_hash)
        else:
          return (bios_version, resource_hash)
      else:
        return (resource_version, resource_hash)

  @staticmethod
  def _IsTagEqual(component, component_tag, resource_tag):
    """Compares component tag and resouce tag."""
    if component in HASH_COMPONENTS:
      return component_tag.startswith(resource_tag)
    return component_tag == resource_tag

  @staticmethod
  def _CanUpdate(stage, range_start, range_end):
    return ((range_start is None or FACTORY_STAGES.index(stage) >=
             FACTORY_STAGES.index(range_start)) and
            (range_end is None or FACTORY_STAGES.index(stage) <=
             FACTORY_STAGES.index(range_end)))

  @RPCCall
  def GetUpdate(self, device_info):
    """Gets factory toolkit update.

    Args:
      device_info: device info dictionary:
        {'x_umpire_dut': {...},
         'components': {
            'rootfs_test': <test_rootfs_version>,
            'rootfs_release': <release_rootfs_version>,
            'firmware_ec': <ec_firmware_version>,
            'firmware_bios': <bios_firmware_version>,
            'hwid': <md5sum_hexstring>,
            'device_factory_toolkit': <md5sum_hexstring>}}

    Returns:
      A dictionary lists update scheme and URL for each requested component:
        {<component_name>: {
            'need_update': boolean flag,
            'scheme': update protocol scheme, http, rsync or zsync,
            'url': URL to the requested resource,
            'md5sum': MD5SUM hex string for the resource},
         <...>
        }
      Or xmlrpc.Fault() on input parsing error.

    Raises:
      KeyError: when required key not in dictionary.
      All exceptions will be caught by umpire.web.xmlrpc and translate to
      proper xmlrpc.Fault() before return.
    """
    update_matrix = {}
    current_stage = device_info['x_umpire_dut']['stage']
    ruleset = SelectRuleset(self.env.config, device_info['x_umpire_dut'])
    logging.debug('ruleset = %s', ruleset)
    bundle_id = ruleset['bundle_id']
    bundle = self.env.config.GetBundle(bundle_id)
    resource_map = bundle['resources']
    enable_update = ruleset.get('enable_update', {})

    for component, component_tag in device_info['components'].iteritems():
      if component not in ALL_COMPONENTS:
        return Fault('%s is not in update component list %s' %
                     (component, str(ALL_COMPONENTS)))

      resource_type = (component if not component.startswith('firmware_') else
                       'firmware')
      resource_filename = resource_map[resource_type]
      resource_tag, resource_hash = self._GetResourceTag(
          component, resource_filename)

      if resource_tag is None:
        return Fault('can not get %s tag from resource %s' %
                     (component, resource_filename))

      if resource_hash is None:
        return Fault('can not get %s hash from resource %s' %
                     (component, resource_filename))

      need_update = False

      if not self._IsTagEqual(component, component_tag, resource_tag):
        # Check if DUT needs an update.
        stage_start, stage_end = enable_update.get(component, (None, None))
        if self._CanUpdate(current_stage, stage_start, stage_end):
          need_update = True

      # Calculate resource
      resource_scheme = None
      resource_url = None
      if component == 'device_factory_toolkit':
        # Select first service provides 'toolkit_update' property.
        update_services = filter(
            lambda s: s.properties.get('toolkit_update', False),
            self.env.config['services'])
        if update_services:
          service = update_services[0]
          resource_scheme = service.properties.get('update_scheme', None)
          resource_url = service.properties.get('update_url', None)
          # Concatenate device toolkit hash.
          if resource_url:
            resource_url = os.path.join(resource_url, resource_hash)
      else:
        resource_scheme = 'http'
        resource_url = 'http://%(ip)s:%(port)d/res/%(filename)s' % {
            'ip': self.env.config['ip'],
            'port': self.env.config['port'],
            'filename': resource_filename}

      update_matrix[component] = {
          'need_update': need_update,
          'md5sum': resource_hash,
          'scheme': resource_scheme,
          'url': resource_url}

    return update_matrix
