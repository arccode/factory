# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# pylint: disable=E1101

"""Common Umpire RPC Commands."""

import glob
import logging
import os
import shutil
import time
from twisted.internet import threads
from twisted.web import xmlrpc
import urllib
import urlparse
import xmlrpclib

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import bundle_selector
from cros.factory.umpire import common
from cros.factory.umpire.service import umpire_service
from cros.factory.umpire import umpire_rpc
from cros.factory.umpire import utils
from cros.factory.utils import file_utils


VERSION_COMPONENTS = ['firmware_bios', 'firmware_ec', 'firmware_pd', 'hwid',
                      'rootfs_test', 'rootfs_release']
HASH_COMPONENTS = ['device_factory_toolkit', 'netboot_firmware']
ALL_COMPONENTS = VERSION_COMPONENTS + HASH_COMPONENTS
# Factory stages in running sequence.
FACTORY_STAGES = ['SMT', 'RUNIN', 'FA', 'GRT']
SYNC_URL = '%{scheme}s://%{ip}s:%{port}d/%{path}s/%{toolkit_md5sum}s/'


def Fault(message, reason=xmlrpclib.INVALID_METHOD_PARAMS):
  """Instanciates an XMLRPC Fault() object.

  xmlrpc.Fault() notifies the RPC client that remote function was terminated
  incorrectly.
  """
  return xmlrpc.Fault(reason, common.UmpireError(message))


class RootDUTCommands(umpire_rpc.UmpireRPC):

  """Root DUT (Device Under Test) remote procedures.

  Root commands for v1 and v2 compatiblilities.

  RPC URL:
    http://umpire_server_address:umpire_port/RPC2
  """

  @umpire_rpc.RPCCall
  def Ping(self):
    return {'version': self.env.umpire_version_major}


class UmpireDUTCommands(umpire_rpc.UmpireRPC):

  """Umpire DUT remote procedures.

  RPC URL:
    http://umpire_server_address:umpire_port/umpire
  """

  @umpire_rpc.RPCCall
  def GetTime(self):
    return time.time()

  @umpire_rpc.RPCCall
  @utils.Deprecate
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
    return [os.path.relpath(x, parameters_dir) for x in matched_file]

  @umpire_rpc.RPCCall
  @utils.Deprecate
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

    return xmlrpc.Binary(file_utils.ReadFile(abspath))

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
    unused_resource_basename, resource_version, resource_hash = (
        utils.ParseResourceName(resource_filename))
    if component in HASH_COMPONENTS:
      return (resource_hash, resource_hash)
    else:
      if component.startswith('firmware_'):
        # Make version list length >= 3
        versions = resource_version.split(':') + [None] * 3
        bios_version, ec_version, pd_version = versions[0:3]
        if component.endswith('_ec'):
          return (ec_version, resource_hash)
        elif component.endswith('_pd'):
          return (pd_version, resource_hash)
        else:
          return (bios_version, resource_hash)
      else:
        return (resource_version, resource_hash)

  @staticmethod
  def _IsTagEqual(component, component_tag, resource_tag):
    """Compares component tag and resouce tag."""
    if component_tag is None:
      return False
    if component in HASH_COMPONENTS:
      return component_tag.startswith(resource_tag)
    return component_tag == resource_tag

  @staticmethod
  def _CanUpdate(stage, range_start, range_end):
    return ((range_start is None or FACTORY_STAGES.index(stage) >=
             FACTORY_STAGES.index(range_start)) and
            (range_end is None or FACTORY_STAGES.index(stage) <=
             FACTORY_STAGES.index(range_end)))

  @umpire_rpc.RPCCall
  @xmlrpc.withRequest
  def GetUpdate(self, request, device_info):
    """Gets factory toolkit update.

    Args:
      device_info: device info dictionary:
        {'x_umpire_dut': {...},
         'components': {
            'rootfs_test': <test_rootfs_version>,
            'rootfs_release': <release_rootfs_version>,
            'firmware_ec': <ec_firmware_version>,
            'firmware_pd': <pd_firmware_version>,
            'firmware_bios': <bios_firmware_version>,
            'hwid': <md5sum_hexstring>,
            'device_factory_toolkit': <md5sum_hexstring>}}

    Returns:
      A dictionary lists update scheme and URL for each requested component:
        {<component_name>: {
            'needs_update': boolean flag,
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
    ruleset = bundle_selector.SelectRuleset(
        self.env.config, device_info['x_umpire_dut'])
    logging.debug('ruleset = %s', ruleset)
    bundle_id = ruleset['bundle_id']
    bundle = self.env.config.GetBundle(bundle_id)
    resource_map = bundle['resources']
    enable_update = ruleset.get('enable_update', {})

    for component, component_tag in device_info['components'].iteritems():
      if component not in ALL_COMPONENTS:
        return Fault('%s is not in update component list %s' %
                     (component, ALL_COMPONENTS))

      resource_type = (component if not component.startswith('firmware_') else
                       'firmware')

      # Factory bundle does not contain the resource_type e.g. netboot_firmware
      if resource_type not in resource_map:
        continue

      resource_filename = resource_map[resource_type]
      resource_tag, resource_hash = self._GetResourceTag(
          component, resource_filename)

      if resource_tag is None:
        return Fault('can not get %s tag from resource %s' %
                     (component, resource_filename))

      if resource_hash is None:
        return Fault('can not get %s hash from resource %s' %
                     (component, resource_filename))

      needs_update = False

      if not self._IsTagEqual(component, component_tag, resource_tag):
        # Check if DUT needs an update.
        stage_start, stage_end = enable_update.get(component, (None, None))
        if self._CanUpdate(current_stage, stage_start, stage_end):
          needs_update = True

      # Calculate resource
      resource_scheme = None
      resource_url = None
      # TODO(crosbug.com/p/52705): no special case should be allowed here.
      if component == 'device_factory_toolkit':
        # Select first service provides 'toolkit_update' property.
        iterable = umpire_service.FindServicesWithProperty(
            self.env.config, 'toolkit_update')
        instance = next(iterable, None)
        if instance and hasattr(instance, 'GetServiceURL'):
          resource_scheme = instance.properties.get('update_scheme', None)
          resource_url = instance.GetServiceURL(self.env)
          if resource_url:
            resource_url = os.path.join(resource_url, resource_hash)
      else:
        resource_scheme = 'http'
        resource_url = 'http://%(ip)s:%(port)d/res/%(filename)s' % {
            'ip': self.env.umpire_ip,
            'port': self.env.umpire_base_port,
            'filename': urllib.quote(resource_filename)}

      if isinstance(resource_url, basestring):
        WILD_HOST = '0.0.0.0'
        parsed_url = urlparse.urlparse(resource_url)
        if parsed_url.netloc.startswith(WILD_HOST):
          server_ip = request.requestHeaders.getRawHeaders('host')[0]
          server_ip = server_ip.split(':')[0]  # may contain port so split it
          logging.debug('Translate IP %s to %s', WILD_HOST, server_ip)
          new_parsed_url = urlparse.ParseResult(
              parsed_url.scheme,
              parsed_url.netloc.replace(WILD_HOST, server_ip, 1),
              parsed_url.path, parsed_url.params, parsed_url.query,
              parsed_url.fragment)
          resource_url = urlparse.urlunparse(new_parsed_url)

      update_matrix[component] = {
          'needs_update': needs_update,
          'md5sum': resource_hash,
          'scheme': resource_scheme,
          'url': resource_url}

    return update_matrix


class LogDUTCommands(umpire_rpc.UmpireRPC):

  """DUT log upload procedures.

  RPC URL:
    http://umpire_server_address:umpire_port/umpire
  """

  def _ReturnTrue(self, result):
    """Returns true."""
    del result  # Unused.
    return True

  def _UnwrapBlob(self, blob):
    """Umwraps a blob object."""
    return blob.data if isinstance(blob, xmlrpclib.Binary) else blob

  def _Now(self):
    """Gets current time."""
    return time.gmtime(time.time())

  def _SaveUpload(self, upload_type, file_name, content, mode='wb'):
    """Saves log file.

    This function saves DUT data. Since file saving is a blocking call,
    _SaveUpload() should be called in a separate thread context.

    Example:
      @umpire_rpc.RPCCall
      def DUTUpload(...)
        d = threads.deferToThread(lambda: self.SaveUpload(type, name, data))
        return d

    Args:
      upload_type: one of LogRPCCommand.LOG_TYPES.
      file_name: full basename of log file.
      content: binary data.
      mode: open file mode. 'wb' to write binary file, 'a' to append file.
    """
    with file_utils.UnopenedTemporaryFile() as temp_path:
      # To support paths in file_name, the save_dir will be splitted after
      # concatenate to full save_path.
      save_path = os.path.join(self.env.umpire_data_dir, upload_type,
                               time.strftime('%Y%m%d', self._Now()),
                               file_name)
      save_dir = os.path.dirname(os.path.abspath(save_path))
      file_utils.TryMakeDirs(save_dir)
      if mode == 'a' and os.path.isfile(save_path):
        shutil.copy2(save_path, temp_path)
      open(temp_path, mode).write(content)
      # Do not use os.rename() to move file. os.rename() behavior is OS
      # dependent.
      shutil.move(temp_path, save_path)
      # temp_path (created by tempfile.mkstemp) will always be mode 0600 for
      # security reason, so we do want to change its permission to u+rw,go+r.
      os.chmod(save_path, 0644)

  @umpire_rpc.RPCCall
  @utils.Deprecate
  def UploadReport(self, serial, report_blob, report_name=None, stage='FA'):
    """Uploads a report file.

    Args:
      serial: A string of device serial number.
      report_blob: Blob of compressed report to be stored (must be prepared by
          shopfloor.Binary)
      report_name: (Optional) Suggested report file name. This is usually
          assigned by factory test client programs (ex, gooftool); however
          server implementations still may use other names to store the report.
      stage: Current testing stage, SMT, RUNIN, FA, or GRT.

    Returns:
      Deferred object that waits for log saving thread to complete.

    RPC returns:
      True on success.

    Raises:
      ValueError if serial is invalid, or other exceptions defined by individual
      modules. Note this will be converted to xmlrpclib.Fault when being used as
      a XML-RPC server module.
    """
    opt_name = ('-' + report_name) if report_name else ''
    file_name = '{stage}{opt_name}-{serial}-{gmtime}.rpt.xz'.format(
        stage=stage, opt_name=opt_name, serial=serial,
        gmtime=time.strftime('%Y%m%dT%H%M%SZ', self._Now()))
    d = threads.deferToThread(lambda: self._SaveUpload(
        'report', file_name, self._UnwrapBlob(report_blob)))
    d.addCallback(self._ReturnTrue)
    return d

  @umpire_rpc.RPCCall
  @utils.Deprecate
  def UploadEvent(self, log_name, chunk):
    """Uploads a chunk of events.

    In addition to append events to a single file, we appends event to a
    directory that split on an daily basis.

    Args:
      log_name: A string of the event log filename. Event logging module creates
          event files with an unique identifier (uuid) as part of the filename.
      chunk: A string containing one or more events. Events are in YAML format
          and separated by a "---" as specified by YAML. A chunk contains one or
          more events with separator.

    Returns:
      Deferred object that waits for log saving thread to complete.

    RPC returns:
      True on success.

    Raises:
      IOError if unable to save the chunk of events.
    """
    d = threads.deferToThread(lambda: self._SaveUpload(
        'eventlog', log_name, self._UnwrapBlob(chunk), mode='a'))
    d.addCallback(self._ReturnTrue)
    return d

  @umpire_rpc.RPCCall
  def SaveAuxLog(self, name, contents):
    """Saves an auxiliary log into the umpire_data/aux_logs directory.

    In general, this should probably be compressed to save space.

    Args:
      name: Name of the report.  Any existing log with the same name will be
        overwritten.  Subdirectories are allowed.
      contents: Contents of the report.  If this is binary, it should be
        wrapped in a shopfloor.Binary object.
    """
    contents = self._UnwrapBlob(contents)

    # Disallow absolute paths and paths with '..'.
    if os.path.isabs(name):
      raise ValueError('Disallow absolute paths')
    if '..' in os.path.split(name):
      raise ValueError('Disallow ".." in paths')

    d = threads.deferToThread(lambda: self._SaveUpload(
        'aux_log', name, self._UnwrapBlob(contents)))
    d.addCallback(self._ReturnTrue)
    return d

  @umpire_rpc.RPCCall
  def GetFactoryLogPort(self):
    """Fetches system logs rsync port."""
    return self.env.umpire_rsync_port
