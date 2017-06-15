# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# pylint: disable=no-member

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

import factory_common  # pylint: disable=unused-import
from cros.factory.umpire import bundle_selector
from cros.factory.umpire import common
from cros.factory.umpire import resource
from cros.factory.umpire.service import umpire_service
from cros.factory.umpire import umpire_env
from cros.factory.umpire import umpire_rpc
from cros.factory.umpire import utils
from cros.factory.utils import file_utils


# Factory stages in running sequence.
FACTORY_STAGES = ['SMT', 'RUNIN', 'FA', 'GRT']


def Fault(message, reason=xmlrpclib.INVALID_METHOD_PARAMS):
  """Instantiates an XMLRPC Fault() object.

  xmlrpc.Fault() notifies the RPC client that remote function was terminated
  incorrectly.
  """
  return xmlrpc.Fault(reason, message)


def GetServerIpPortFromRequest(request, env):
  server_host = request.requestHeaders.getRawHeaders('host')[0]
  server_ip, unused_sep, server_port = server_host.partition(':')

  # The Host HTTP header do contains port when using xmlrpclib.ServerProxy,
  # but it doesn't contains port when using twisted.web.xmlrpc.Proxy.
  # Since currently the only places that use twisted.web.xmlrpc.Proxy are
  # all inside unittests, and the returned url is not used in unittests, we
  # just add some default value to prevent unittest from failing.
  # TODO(pihsun): Figure out a better way to handle the case when port is
  # missing from Host header.
  server_port = int(server_port or env.umpire_base_port)
  return (server_ip, server_port)


class RootDUTCommands(umpire_rpc.UmpireRPC):
  """Root DUT (Device Under Test) remote procedures.

  Root commands for v1 and v2 compatibilities.

  RPC URL:
    http://umpire_server_address:umpire_port/RPC2
  """

  @umpire_rpc.RPCCall
  def Ping(self):
    return {'version': common.UMPIRE_VERSION}


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
    payloads = self.env.GetPayloadsDict(bundle['payloads'])
    enable_update = ruleset.get('enable_update', {})

    for dut_component_name, dut_component_tag in device_info[
        'components'].iteritems():
      # TODO(youcheng): Support release_image.
      try:
        if dut_component_name == 'device_factory_toolkit':
          type_name = resource.PayloadTypeNames.toolkit
        elif dut_component_name == 'hwid':
          type_name = resource.PayloadTypeNames.hwid
        elif dut_component_name.startswith('firmware_'):
          type_name = resource.PayloadTypeNames.firmware
        else:
          continue
        payload = payloads[type_name]
        res_hash = resource.GetFilePayloadHash(payload)
        res_name = payload['file']
        if type_name == resource.PayloadTypeNames.toolkit:
          # TODO(b/36083439): Use version to determine if toolkit update is
          #                   necessary.
          res_tag = res_hash
        else:
          # TODO(youcheng): Needs special rule for firmware. cros_payload
          #                 doesn't provide firmware version in desired format.
          #                 This will always report needs_update=True for now.
          res_tag = payload['version']
      except Exception:
        continue

      needs_update = False

      if dut_component_tag != res_tag:
        # Check if DUT needs an update.
        stage_start, stage_end = enable_update.get(dut_component_name,
                                                   (None, None))
        if self._CanUpdate(current_stage, stage_start, stage_end):
          needs_update = True

      # Calculate resource
      res_scheme = None
      res_url = None

      # Use the ip and port from request headers, since the ip and port in
      # self.env.{umpire_ip, umpire_base_port} are ip / port inside docker,
      # but we need to return the ip / port used outside docker.
      server_ip, server_port = GetServerIpPortFromRequest(request, self.env)

      # TODO(crosbug.com/p/52705): no special case should be allowed here.
      if dut_component_name == 'device_factory_toolkit':
        # Select first service provides 'toolkit_update' property.
        iterable = umpire_service.FindServicesWithProperty(
            self.env.config, 'toolkit_update')
        instance = next(iterable, None)
        if instance and hasattr(instance, 'GetServiceURL'):
          res_scheme = instance.properties.get('update_scheme', None)
          res_url = instance.GetServiceURL(server_ip, server_port)
          if res_url:
            res_url = '%s/%s' % (res_url, res_hash)
      else:
        res_scheme = 'http'
        res_url = 'http://%(ip)s:%(port)d/res/%(filename)s' % {
            'ip': server_ip,
            'port': server_port,
            'filename': urllib.quote(res_name)}

      update_matrix[dut_component_name] = {
          'needs_update': needs_update,
          'md5sum': res_hash,
          'scheme': res_scheme,
          'url': res_url}

    return update_matrix


class ShopfloorServiceDUTCommands(umpire_rpc.UmpireRPC):
  """Shopfloor Service for DUT (Device Under Test) to invoke.

  RPC URL:
    http://umpire_server_address:umpire_port/umpire
  """

  def __init__(self, daemon, service_url):
    super(ShopfloorServiceDUTCommands, self).__init__(daemon)
    self.service = xmlrpclib.ServerProxy(service_url.rstrip('/'),
                                         allow_none=True)

  @umpire_rpc.RPCCall
  def GetVersion(self):
    """Returns the version of supported protocol."""
    return self.service.GetVersion()

  @umpire_rpc.RPCCall
  def NotifyStart(self, data, station):
    """Notifies shopfloor backend that DUT entered a manufacturing station."""
    return self.service.NotifyStart(data, station)

  @umpire_rpc.RPCCall
  def NotifyEnd(self, data, station):
    """Notifies shopfloor backend that DUT leaves a manufacturing station."""
    return self.service.NotifyEnd(data, station)

  @umpire_rpc.RPCCall
  def NotifyEvent(self, data, event):
    """Notifies shopfloor backend that the DUT has performed an event."""
    return self.service.NotifyEvent(data, event)

  @umpire_rpc.RPCCall
  def GetDeviceInfo(self, data):
    """Returns information about the device's expected configuration."""
    return self.service.GetDeviceInfo(data)

  @umpire_rpc.RPCCall
  def ActivateRegCode(self, ubind_attribute, gbind_attribute, hwid):
    """Notifies shopfloor backend that DUT has deployed a registration code."""
    return self.service.ActivateRegCode(ubind_attribute, gbind_attribute, hwid)

  @umpire_rpc.RPCCall
  def UpdateTestResult(self, data, test_id, status, details=None):
    """Sends the specified test result to shopfloor backend."""
    return self.service.UpdateTestResult(data, test_id, status, details)

  @umpire_rpc.RPCCall
  @utils.Deprecate
  def Finalize(self, serial_number):
    """Legacy from inform_shopfloor, not in Shopfloor Service API 1.0."""
    return self.NotifyEvent({'serial_number': serial_number}, 'Finalize')

  @umpire_rpc.RPCCall
  @utils.Deprecate
  def FinalizeFQC(self, serial_number):
    """Legacy from inform_shopfloor, not in Shopfloor Service API 1.0."""
    return self.NotifyEvent({'serial_number': serial_number}, 'Refinalize')


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
    """Unwraps a blob object."""
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
      # temp_path (created by UnopenedTemporaryFile) will always be mode 0600
      # for security reason, so we do want to change its permission to
      # u+rw,go+r.
      os.chmod(save_path, 0644)

  @umpire_rpc.RPCCall
  @utils.Deprecate
  def UploadReport(self, serial, report_blob, report_name=None, stage=None):
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
        stage=stage or 'FA', opt_name=opt_name, serial=serial,
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
  @xmlrpc.withRequest
  def GetFactoryLogPort(self, request):
    """Fetches system logs rsync port."""
    unused_server_ip, server_port = GetServerIpPortFromRequest(
        request, self.env)
    return umpire_env.GetRsyncPortFromBasePort(server_port)

  @umpire_rpc.RPCCall
  @xmlrpc.withRequest
  def GetInstalogPort(self, request):
    """Fetches Instalog port."""
    unused_server_ip, server_port = GetServerIpPortFromRequest(
        request, self.env)
    return umpire_env.GetInstalogPortFromBasePort(server_port)
