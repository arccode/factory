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
import urllib
import xmlrpclib
from twisted.internet import threads
from twisted.web import xmlrpc

import factory_common  # pylint: disable=W0611
from cros.factory.umpire.bundle_selector import SelectRuleset
from cros.factory.umpire.common import ParseResourceName, UmpireError
from cros.factory.umpire.service.umpire_service import FindServicesWithProperty
from cros.factory.umpire.umpire_rpc import RPCCall, UmpireRPC
from cros.factory.umpire.utils import Deprecate
from cros.factory.utils import file_utils


VERSION_COMPONENTS = ['firmware_bios', 'firmware_ec', 'firmware_pd', 'hwid',
                      'rootfs_test', 'rootfs_release']
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
    return [os.path.relpath(x, parameters_dir) for x in matched_file]

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

      needs_update = False

      if not self._IsTagEqual(component, component_tag, resource_tag):
        # Check if DUT needs an update.
        stage_start, stage_end = enable_update.get(component, (None, None))
        if self._CanUpdate(current_stage, stage_start, stage_end):
          needs_update = True

      # Calculate resource
      resource_scheme = None
      resource_url = None
      if component == 'device_factory_toolkit':
        # Select first service provides 'toolkit_update' property.
        iterable = FindServicesWithProperty(self.env.config, 'toolkit_update')
        instance = next(iterable, None)
        if instance:
          resource_scheme = instance.properties.get('update_scheme', None)
          resource_url = instance.properties.get('update_url', None)
          if resource_url:
            resource_url = os.path.join(resource_url, resource_hash)
      else:
        resource_scheme = 'http'
        resource_url = 'http://%(ip)s:%(port)d/res/%(filename)s' % {
            'ip': self.env.config['ip'],
            'port': self.env.config['port'],
            'filename': urllib.quote(resource_filename)}

      update_matrix[component] = {
          'needs_update': needs_update,
          'md5sum': resource_hash,
          'scheme': resource_scheme,
          'url': resource_url}

    return update_matrix


class LogDUTCommands(UmpireRPC):

  """DUT log upload procedures.

  RPC URL:
    http://umpire_server_address:umpire_port/umpire
  """

  def _ReturnTrue(self, unused_result):
    """Returns true."""
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
      @RPCCall
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
      # To support pathes in file_name, the save_dir will be splitted after
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
      # depandent.
      shutil.move(temp_path, save_path)

  @RPCCall
  @Deprecate
  def UploadReport(self, serial, report_blob, report_name=None, stage='FA'):
    """Uploads a report file.

    Args:
      serial: A string of device serial number.
      report_blob: Blob of compressed report to be stored (must be prepared by
          shopfloor.Binary)
      report_name: (Optional) Suggested report file name. This is uslally
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

  @RPCCall
  @Deprecate
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

  @RPCCall
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
      raise ValueError('Disallow absolute pathes')
    if '..' in os.path.split(name):
      raise ValueError('Disallow ".." in pathes')

    d = threads.deferToThread(lambda: self._SaveUpload(
        'aux_log', name, self._UnwrapBlob(contents)))
    d.addCallback(self._ReturnTrue)
    return d

  @RPCCall
  def GetFactoryLogPort(self):
    """Fetches system logs rsync port."""
    return self.env.umpire_rsync_port()
