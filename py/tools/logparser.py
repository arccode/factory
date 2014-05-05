#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module is used for log uploading on AB-sub line.
Once log uploaded, log file will be decompressed and remove to a specified
directory.
"""

import cgi
import datetime
import factory_common  # pylint: disable=W0611
import fcntl
import optparse
import os
import re
import tarfile
import threading
import yaml
import zipfile

from cros.factory.schema import (AnyOf, Dict, FixedDict, List,
                                 Scalar, SchemaException)
from flup.server.fcgi import WSGIServer

# Directory setting
_BASE_DIR = '/var/www'
_TAR_FILE_DIR = '%s/tarfiles' % _BASE_DIR
_RAW_DATA_DIR = '%s/rawdata' % _BASE_DIR
_EVENT_LOG_DIR = '%s/eventlog' % _BASE_DIR
_VPD_FILE = '%s/tarfiles/vpd' % _BASE_DIR

# File pattern setting
_SERIAL_DIGIT = 5
_FILE_NAME_RE = re.compile(r'(\w+?)_(\d{%d})_(\d{17})$' % _SERIAL_DIGIT)
_FILE_EXT_RE = re.compile(r'.(tgz|zip|tar)$')

# Event Log setting
_SYNC_MARKER = '#s\n'


class WSGISession(object):
  """WSGI session class.

  This class provides shortcuts to access encapsulated WSGI environ dict and
  start_response functor.

  Args:
    environ: WSGI env dictionary.
    query_string: A dictionary to store key-value paris from HTTP request.
    start_response: WSGI response functor for sending HTTP response headers.
  """
  BUFFER_SIZE = 1024 * 200

  def __init__(self, environ, start_response, *args, **kwargs):
    super(WSGISession, self).__init__(*args, **kwargs)
    self.environ = environ
    self.start_response = start_response
    self.query_string = {}
    self._HandleQuery()

  def _HandleQuery(self):
    if not self.environ['QUERY_STRING']:
      return
    params = self.environ['QUERY_STRING'].split('&')
    for pair in params:
      values = pair.split('=')
      self.query_string[values[0]] = '='.join(values[1:])

  def Method(self):
    """Gets WSGI request method."""
    return self.environ['REQUEST_METHOD']

  def _ContentLength(self):
    """Gets numerical WSGI request content length."""
    return int(self.environ.get('CONTENT_LENGTH', 0))

  def Read(self):
    """Reads from WSGI input stream file object."""
    length = self._ContentLength()
    stream = self.environ['wsgi.input']
    buf = []
    while length > 0:
      part = stream.read(min(length, self.BUFFER_SIZE))
      if not part:
        break
      buf.append(part)
      length -= len(part)
    return ''.join(buf)

  def GetFile(self):
    """Gets a FieldStorage object contains file information from POST request.

    HTTP POST request should upload one file in a session.

    Returns:
      A FieldStorage object:
          {name: field_name, filename: file_name, value: file_content}
      None: If there are multiple files uploaded or no file uploaded.
    """
    form = cgi.FieldStorage(fp=self.environ['wsgi.input'],
                            environ=self.environ,
                            keep_blank_values=True)
    if len(form) != 1:
      return None
    for key in form.keys():
      return form[key]
    return None

  def GetQuery(self, key):
    return self.query_string.get(key, None)

  def Response(self, content_type, data):
    """Generates WSGI '200 OK' HTTP response.

    Args:
      content_type: IANA media types.
      data: the response body.

    Returns:
      WSGI return body list.
    """
    headers = [('Content-Type', content_type),
               ('Content-Length', str(len(data)))]
    self.start_response('200 OK', headers)
    return [data]


class LogParser(object):
  """Validates log format and saves it to a specified directory.

  It is an WSGIServer application which return VPD Data for GET request and
  stores uploaded file for POST request.
  """
  SCHEMA = FixedDict(
      'Log upload config',
      items={
          'panel_serial': Scalar('Serial number', str),
          'timestamp': Scalar('Time stamp', datetime.datetime),
          'fixture_id': Scalar('Fixture ID', str),
          'status': Scalar('Status', str),
          'duration': AnyOf([
              Scalar('Duration', int),
              Scalar('Duration', float),
          ], 'Duration'),
      },
      optional_items={
          'vpd': Dict('VPD', Scalar('key', str), AnyOf([
              Scalar('Value', str),
              Scalar('Value', int),
              Scalar('Value', float),
          ], 'Value')),
          'rawdata': List('Rawdata', Scalar('Files', str)),
      })

  def __init__(self, options=None):
    """Constructor

    Args:
      options: contains directories setting.
    """
    if not options:
      options = dict()
    self.tarfile_dir = options.get('tarfile_dir', _TAR_FILE_DIR)
    self.rawdata_dir = options.get('rawdata_dir', _RAW_DATA_DIR)
    self.eventlog_dir = options.get('eventlog_dir', _EVENT_LOG_DIR)
    self.vpd_file = options.get('vpd_file', _VPD_FILE)

    self._CreateDir(self.tarfile_dir)
    self._CreateDir(self.rawdata_dir)
    self._CreateDir(self.eventlog_dir)
    self._CreateDir(os.path.dirname(self.vpd_file))

    self.vpd_lock = threading.Lock()
    self.vpd = {}
    self._LoadVPD()

  def __call__(self, environ, start_response):
    session = WSGISession(environ, start_response)
    ret = ''
    if session.Method() == 'POST':
      try:
        self.CheckUploadFile(session)
      except Exception as e:
        ret = 'FAILED, %s' % e
      else:
        ret = 'PASSED'
    elif session.Method() == 'GET':
      ret = self.GetVPDData(session)
    return session.Response('text/plain', str(ret))

  def _CreateDir(self, path):
    if not os.path.exists(path):
      os.makedirs(path)

  def GetVPDData(self, session):
    """Gets all key-value pairs of VPD data.

    HTTP GET request contains 'serial' information. Logparser should return
    VPD data of this serial number.

    Args:
      session: an WSGISession object.

    Returns:
      VPD data for the serial specified in session object.
      None if the serial doesn't have VPD data.
    """
    serial = session.GetQuery('serial')
    if serial in self.vpd:
      return self.vpd[serial]
    return None

  def CheckUploadFile(self, session):
    """Handles the uploaded file from HTTP POST request.

    This function also check the format of log files and move log files to a
    specified directory.

    Args:
      session: an WSGISession object.

    Raises:
      Exception when uploaded file name incorrect.
    """
    fileitem = session.GetFile()
    if fileitem is None:
      raise Exception('No file or multiple files upload.')

    # file_desc is the target of decompressed file, which is derived from
    # uploaded filename.
    file_desc = self.ParseFileName(fileitem.filename)

    file_path = os.path.join(self.tarfile_dir, fileitem.filename)
    with open(file_path, 'w') as f:
      f.write(fileitem.value)

    self.DecompressFile(file_path, file_desc)

    log_desc = self.LoadDescription(file_desc)

    self.UpdateVPD(log_desc)
    self.ExportEventLog(log_desc)

  def UpdateVPD(self, log_desc):
    """Updates VPD dictionary and writes to a file.

    Args:
      log_desc: a dict of uploaded logs description
    """
    if 'vpd' not in log_desc:
      return
    panel_serial = log_desc['panel_serial']
    if panel_serial not in self.vpd:
      self.vpd[panel_serial] = {}

    self.vpd[panel_serial].update(log_desc['vpd'])
    self._ExportVPD()

  def ExportEventLog(self, log_desc):
    """Exports event logs to file.

    Event logs are put according to date. The log file will be
    ${EVENT_LOG_DIR}/${DATE}/events.${PANEL_SERIAL}

    Args:
      log_desc: a dict of uploaded logs description
    """
    log_path = os.path.join(self.eventlog_dir,
                            log_desc['timestamp'].strftime('%Y%m%d'))
    if not os.path.exists(log_path):
      os.makedirs(log_path)
    log_file = os.path.join(log_path, 'events.%s' % log_desc['panel_serial'])
    with open(log_file, 'a') as event_file:
      data = {
          'EVENT': 'fixture_log',
          'PANEL_SERIAL': log_desc['panel_serial'],
          'TIME': log_desc['timestamp'],
          'STATUS': log_desc['status'],
          'DURATION': log_desc['duration'],
          'FIXTURE_ID': log_desc['fixture_id'],
      }
      data.update(log_desc['events'])
      yaml_data = yaml.dump(data) + _SYNC_MARKER + '---\n'
      fcntl.flock(event_file.fileno(), fcntl.LOCK_EX)
      try:
        event_file.write(yaml_data)
        event_file.flush()
      finally:
        fcntl.flock(event_file.fileno(), fcntl.LOCK_UN)
      os.fdatasync(event_file.fileno())

  def GetFilePath(self, file_desc, *file_name):
    """Generates file path according to file_desc."""
    return os.path.join(
        self.rawdata_dir,
        file_desc['fixture_id'],
        file_desc['serial_number'],
        file_desc['time_stamp'],
        *file_name)

  def LoadDescription(self, file_desc):
    """Loads description file and checks file schema format.

    Checks file schema and the consistency of file_desc and file content.

    Args:
      file_desc: information of the file

    Raises:
      SchemaException when schema format incorrect.
      Exception when file does not exist or mismatch between file_desc and
      file content.
    """
    log_desc = None
    file_path = self.GetFilePath(file_desc, 'description.yaml')
    if not os.path.exists(file_path):
      raise Exception('description.yaml does not exist.')

    with open(file_path, 'r') as desc_file:
      log_desc = yaml.load(desc_file)

    try:
      self.SCHEMA.Validate(log_desc)
    except SchemaException as e:
      # We don't check events format
      if not str(e).startswith('Keys [\'events\'] are undefined in FixedDict'):
        raise

    # Check panel serial
    if log_desc['panel_serial'] != file_desc['serial_number']:
      raise Exception('Panel serial %r does not match with filename %r.' % (
          log_desc['panel_serial'], file_desc['serial_number']))

    # Check time stamp
    t = log_desc['timestamp'].strftime('%Y%m%d%H%M%S%f')[:-3]
    if t != file_desc['time_stamp']:
      raise Exception('Timestamp %r does not match with filename %r.' % (
          t, file_desc['time_stamp']))

    # Check fixture ID
    if log_desc['fixture_id'] != file_desc['fixture_id']:
      raise Exception('Fixture ID %r does not match with filename %r.' % (
          log_desc['fixture_id'], file_desc['fixture_id']))

    # Check status
    if log_desc['status'] not in ['PASSED', 'FAILED']:
      raise Exception('Status should be PASSED or FAILED.')

    # Check rawdata
    if 'rawdata' in log_desc:
      for file_name in log_desc['rawdata']:
        path = self.GetFilePath(file_desc, file_name)
        if not os.path.exists(path):
          raise Exception('Raw data %s does not exist.' % file_name)
    return log_desc

  def ParseFileName(self, file_name):
    """Checks and parses file name format.

    Args:
      file_name: The name of a file

    Returns:
      File_description: The information of this file name.

    Raises:
      Exception when file name does not match the rule.
    """
    file_desc = {}
    root_name, ext = os.path.splitext(file_name)
    m = _FILE_EXT_RE.match(ext)
    if not m:
      raise Exception('File extension should be tgz or zip.')

    m = _FILE_NAME_RE.match(root_name)
    if not m:
      raise Exception('File name %s does not match pattern.' % file_name)
    file_desc['fixture_id'] = m.group(1)
    file_desc['serial_number'] = m.group(2)
    file_desc['time_stamp'] = m.group(3)
    return file_desc

  def DecompressZip(self, file_path, target_path):
    """Decompresses ZIP format file

    Args:
      file_path: the path of compressed file
      target_path: the path of extracted files

    Returns:
      True if file is a ZIP format file
    """
    if not zipfile.is_zipfile(file_path):
      return False
    with zipfile.ZipFile(file_path) as zf:
      zf.extractall(target_path)
    return True

  def DecompressTar(self, file_path, target_path):
    """Decompresses TAR format file

    Supports TAR and TAR+GZIP format.

    Args:
      file_path: the path of compressed file
      target_path: the path of extracted files

    Returns:
      True if file is a TAR format file
    """
    if not tarfile.is_tarfile(file_path):
      return False
    with tarfile.open(file_path) as tf:
      tf.extractall(target_path)
    return True

  def DecompressFile(self, file_path, file_desc):
    """Decompresses file

    Args:
      file_path: the path of compressed file
      file_desc: information of the file to generate target path

    Raises:
      Unsupport format exception if file format is not ZIP/TAR/TGZ.
    """
    target_path = self.GetFilePath(file_desc)
    if not os.path.exists(target_path):
      os.makedirs(target_path)

    if self.DecompressZip(file_path, target_path):
      return
    if self.DecompressTar(file_path, target_path):
      return
    raise Exception('Unsupport format.')

  def _LoadVPD(self):
    if not os.path.exists(self.vpd_file):
      return
    with self.vpd_lock:
      with open(self.vpd_file, 'r') as vpd_file:
        self.vpd = yaml.load(vpd_file)

  def _ExportVPD(self):
    data = yaml.dump(self.vpd)
    with self.vpd_lock:
      with open(self.vpd_file, 'w') as vpd_file:
        vpd_file.write(data)
        vpd_file.flush()


def main():
  parser = optparse.OptionParser()
  parser.add_option('-t', '--tar-file-dir', dest='tarfile_dir',
                    metavar='TARFILE_DIR', default=_TAR_FILE_DIR,
                    help='data directory for compressed file')
  parser.add_option('-r', '--raw-data-dir', dest='rawdata_dir',
                    metavar='RAWDATA_DIR', default=_RAW_DATA_DIR,
                    help='data directory for decompressed files')
  parser.add_option('-e', '--event-log-dir', dest='eventlog_dir',
                    metavar='EVENTLOG_DIR', default=_EVENT_LOG_DIR,
                    help='log directory for all events')
  parser.add_option('-v', '--vpd-file', dest='vpd_file',
                    metavar='VPD_FILE', default=_VPD_FILE,
                    help='file to store vpd information')
  (options, _) = parser.parse_args()

  params = {
      'tarfile_dir': options.tarfile_dir,
      'rawdata_dir': options.rawdata_dir,
      'eventlog_dir': options.eventlog_dir,
      'vpd_file': options.vpd_file}
  logparser = LogParser(params)
  WSGIServer(logparser).run()


if __name__ == '__main__':
  main()
