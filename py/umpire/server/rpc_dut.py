# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common Umpire RPC Commands."""

import csv
import glob
import os
import shutil
import tarfile
import time
import xmlrpc.client

from twisted.internet import threads
from twisted.web import xmlrpc as twisted_xmlrpc

from cros.factory.umpire import common
from cros.factory.umpire.server import umpire_env
from cros.factory.umpire.server import umpire_rpc
from cros.factory.umpire.server import utils
from cros.factory.utils import file_utils
from cros.factory.utils import webservice_utils


def Fault(message, reason=xmlrpc.client.INVALID_METHOD_PARAMS):
  """Instantiates an XMLRPC Fault() object.

  twisted_xmlrpc.Fault() notifies the RPC client that remote function was
  terminated incorrectly.
  """
  return twisted_xmlrpc.Fault(reason, message)


def GetServerIpPortFromRequest(request, env):
  server_host = request.requestHeaders.getRawHeaders('host')[0]
  server_ip, unused_sep, server_port = server_host.partition(':')

  # The Host HTTP header do contains port when using xmlrpc.client.ServerProxy,
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
    return {
        'version': common.UMPIRE_DUT_RPC_VERSION,
        'project': self.env.project
    }


class UmpireDUTCommands(umpire_rpc.UmpireRPC):
  """Umpire DUT remote procedures.

  RPC URL:
    http://umpire_server_address:umpire_port/umpire
  """

  @umpire_rpc.RPCCall
  def GetTime(self):
    return time.time()

  # TODO(hsinyi): Remove ListParameters and GetParameter and modify related
  #               pytest codes.
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
    matched_file = list(filter(os.path.isfile, matched_file))
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

    return twisted_xmlrpc.Binary(file_utils.ReadFile(abspath, encoding=None))

  @umpire_rpc.RPCCall
  def GetParameters(self, namespace=None, name=None):
    """Gets parameter components by querying namespace and component name.

    Args:
      namespace: relative directory path of queried component(s). None if
                 they are in root directory.
      name: component name of queried component. None if targeting all
            components under namespace.

    Returns:
      Content of the parameter. It is always wrapped in a shopfloor.Binary
      object to provides best flexibility.

    Raises:
      ValueError if the parameter does not exist.
    """
    abspaths = self.env.parameters.QueryParameters(namespace, name)

    if not abspaths:
      raise ValueError('File does not exist or it is not a file')

    # Pack files to tar
    with file_utils.UnopenedTemporaryFile() as tar_path:
      tar = tarfile.open(tar_path, 'w')
      for arcname, path in abspaths:
        tar.add(path, arcname=arcname)
      tar.close()
      return twisted_xmlrpc.Binary(file_utils.ReadFile(tar_path, encoding=None))

  @umpire_rpc.RPCCall
  @twisted_xmlrpc.withRequest
  def GetCROSPayloadURL(self, request, x_umpire_dut):
    """Gets cros_payload JSON file URL of the matched bundle.

    Args:
      x_umpire_dut: DUT information in GetXUmpireDUT (str) or _GetXUmpireDUTDict
        (dict) format.

    Returns:
      URL of cros_payload JSON file, or empty string if no available bundle.
    """
    del x_umpire_dut  # Unused.
    bundle = self.env.config.GetActiveBundle()
    if bundle:
      return 'http://%s:%d/res/%s' % (
          GetServerIpPortFromRequest(request, self.env) + (bundle['payloads'],))
    return ''


class ShopfloorServiceDUTCommands(umpire_rpc.UmpireRPC):
  """Shopfloor Service for DUT (Device Under Test) to invoke.

  RPC URL:
    http://umpire_server_address:umpire_port/umpire
  """

  def __init__(self, daemon):
    super(ShopfloorServiceDUTCommands, self).__init__(daemon)
    # Reuse ServerProxy so that we don't need to create a new one for every
    # request.
    self._url = None
    self._proxy = None

  @property
  def service(self):
    url = self.env.shopfloor_service_url
    if self._url != url:
      self._proxy = webservice_utils.CreateWebServiceProxy(
          url, use_twisted=True)
      self._url = url
    return self._proxy

  @umpire_rpc.RPCCall
  def GetVersion(self):
    """Returns the version of supported protocol."""
    return self.service.callRemote('GetVersion')

  @umpire_rpc.RPCCall
  def NotifyStart(self, data, station):
    """Notifies shopfloor backend that DUT entered a manufacturing station."""
    return self.service.callRemote('NotifyStart', data, station)

  @umpire_rpc.RPCCall
  def NotifyEnd(self, data, station):
    """Notifies shopfloor backend that DUT leaves a manufacturing station."""
    return self.service.callRemote('NotifyEnd', data, station)

  @umpire_rpc.RPCCall
  def NotifyEvent(self, data, event):
    """Notifies shopfloor backend that the DUT has performed an event."""
    return self.service.callRemote('NotifyEvent', data, event)

  @umpire_rpc.RPCCall
  def GetDeviceInfo(self, data):
    """Returns information about the device's expected configuration."""
    return self.service.callRemote('GetDeviceInfo', data)

  @umpire_rpc.RPCCall
  def ActivateRegCode(self, ubind_attribute, gbind_attribute, hwid):
    """Notifies shopfloor backend that DUT has deployed a registration code."""
    return self.service.callRemote('ActivateRegCode', ubind_attribute,
                                   gbind_attribute, hwid)

  @umpire_rpc.RPCCall
  def UpdateTestResult(self, data, test_id, status, details=None):
    """Sends the specified test result to shopfloor backend."""
    return self.service.callRemote('UpdateTestResult', data, test_id, status,
                                   details)

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


class NewlineTerminatedCSVDialect(csv.excel):
  lineterminator = '\n'


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
    return blob.data if isinstance(blob, xmlrpc.client.Binary) else blob

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
                               time.strftime('%Y%m%d', self._Now()), file_name)
      save_dir = os.path.dirname(os.path.abspath(save_path))
      file_utils.TryMakeDirs(save_dir)
      if mode == 'ab' and os.path.isfile(save_path):
        shutil.copy2(save_path, temp_path)
      with open(temp_path, mode) as f:
        f.write(content)
      # Do not use os.rename() to move file. os.rename() behavior is OS
      # dependent.
      shutil.move(temp_path, save_path)
      # temp_path (created by UnopenedTemporaryFile) will always be mode 0600
      # for security reason, so we do want to change its permission to
      # u+rw,go+r.
      os.chmod(save_path, 0o644)

  def _AppendCSV(self, file_name, entry, mode='a'):
    """Saves an entry to CSV file."""
    file_utils.TryMakeDirs(os.path.dirname(file_name))
    with open(file_name, mode) as f:
      csv.writer(f, dialect=NewlineTerminatedCSVDialect).writerow(entry)
      os.fdatasync(f.fileno())

  @umpire_rpc.RPCCall
  def UploadReport(self, serial, report_blob, report_name=None, stage=None):
    """Uploads a report file.

    Args:
      serial: A string of device serial number.
      report_blob: Blob of compressed report to be stored (must be prepared by
          shopfloor.Binary)
      report_name: (Optional) Suggested report file name. This is usually
          assigned by factory test client programs (ex, gooftool); however
          server implementations still may use other names to store the report.
      stage: (Optional) Current testing stage: SMT, FAT, RUNIN, FFT, or GRT.

    Returns:
      Deferred object that waits for log saving thread to complete.

    RPC returns:
      True on success.

    Raises:
      ValueError if serial is invalid, or other exceptions defined by individual
      modules. Note this will be converted to xmlrpc.client.Fault when being
      used as a XML-RPC server module.
    """
    opt_name = ('-' + report_name) if report_name else ''
    file_name = '{stage}{opt_name}-{serial}-{gmtime}.rpt.xz'.format(
        stage=stage or 'Unknown', opt_name=opt_name, serial=serial,
        gmtime=time.strftime('%Y%m%dT%H%M%SZ', self._Now()))
    d = threads.deferToThread(lambda: self._SaveUpload(
        'report', file_name, self._UnwrapBlob(report_blob)))
    d.addCallback(self._ReturnTrue)
    return d

  @umpire_rpc.RPCCall
  def UploadCSVEntry(self, csv_name, data):
    """Uploads a list-type data and save in CSV file.

    This is usually used for storing device data that should not be associated
    with device identifiers (like device serial number), for example
    registration codes.

    Devices that can be associated with serial numbers should use TestLog.

    Args:
      csv_name: The base file name of target CSV file, without suffix.
      data: A list or entry to be appended into CSV file.
    """
    file_name = os.path.join(self.env.umpire_data_dir, 'csv', csv_name + '.csv')
    d = threads.deferToThread(lambda: self._AppendCSV(file_name, data))
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
        'eventlog', log_name, self._UnwrapBlob(chunk), mode='ab'))
    d.addCallback(self._ReturnTrue)
    return d

  @umpire_rpc.RPCCall
  @utils.Deprecate
  def SaveAuxLog(self, name, contents):
    """Saves an auxiliary log into the umpire_data/aux_logs directory.

    In general, this should probably be compressed to save space.

    Args:
      name: Name of the report.  Any existing log with the same name will be
        overwritten.  Subdirectories are allowed.
      contents: Contents of the report.  If this is binary, it should be
        wrapped in a shopfloor.Binary object.
    """
    # Disallow absolute paths and non-normalized paths.
    if os.path.isabs(name):
      raise ValueError('Disallow absolute paths')
    if name != os.path.normpath(name):
      raise ValueError('Disallow non-normalized paths')

    d = threads.deferToThread(
        lambda: self._SaveUpload('aux_log', name, self._UnwrapBlob(contents)))
    d.addCallback(self._ReturnTrue)
    return d

  @umpire_rpc.RPCCall
  @twisted_xmlrpc.withRequest
  def GetFactoryLogPort(self, request):
    """Fetches system logs rsync port."""
    unused_server_ip, server_port = GetServerIpPortFromRequest(
        request, self.env)
    return umpire_env.GetRsyncPortFromBasePort(server_port)
