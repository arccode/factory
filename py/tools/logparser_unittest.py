#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import cgi
import copy
import os
import shutil
import tarfile
import tempfile
import unittest
import yaml
import zipfile

import factory_common  # pylint: disable=W0611
from cros.factory.tools.logparser import LogParser, WSGISession
from mock import patch

_UNITTEST_ROOT = '/tmp/logparser_unittest'
_TAR_FILE_DIR = '%s/tarfiles' % _UNITTEST_ROOT
_RAW_DATA_DIR = '%s/rawdata' % _UNITTEST_ROOT
_EVENT_LOG_DIR = '%s/eventlog' % _UNITTEST_ROOT
_VPD_FILE = '%s/tarfiles/vpd' % _UNITTEST_ROOT
_CAMERA_FILE = '%s/tarfiles/camera_mapping' % _UNITTEST_ROOT

_TMP_COMPRESS_DIR = '%s/tmp' % _UNITTEST_ROOT


class LogParserUnitTest(unittest.TestCase):
  GET_ENVIRON_SAMPLE = {
      'wsgi.multiprocess': False,
      'REDIRECT_STATUS': '200',
      'SERVER_SOFTWARE': 'lighttpd/1.4.28',
      'SCRIPT_NAME': '/getvpd',
      'REQUEST_METHOD': 'GET',
      'PATH_INFO': '/getvpd',
      'SERVER_PROTOCOL': 'HTTP/1.1',
      'QUERY_STRING': '',
      'HTTP_USER_AGENT': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                         '(KHTML, like Gecko) Chrome/34.0.1847.116 '
                         'Safari/537.36',
      'HTTP_CONNECTION': 'keep-alive',
      'SERVER_NAME': '127.0.0.1',
      'REMOTE_PORT': '42437',
      'wsgi.url_scheme': 'http',
      'SERVER_PORT': '80',
      'SERVER_ADDR': '127.0.0.1',
      'DOCUMENT_ROOT': '/var/www',
      'SCRIPT_FILENAME': '/var/www/getvpd',
      'wsgi.input': None,
      'HTTP_HOST': '127.0.0.1',
      'wsgi.multithread': True,
      'HTTP_CACHE_CONTROL': 'max-age=0',
      'REQUEST_URI': '/getvpd',
      'HTTP_ACCEPT': 'text/html,application/xhtml+xml,application/xml;'
                     'q=0.9,image/webp,*/*;q=0.8',
      'wsgi.version': (1, 0),
      'GATEWAY_INTERFACE': 'CGI/1.1',
      'wsgi.run_once': False,
      'wsgi.errors': None,
      'REMOTE_ADDR': '127.0.0.1',
      'HTTP_ACCEPT_LANGUAGE': 'en-US,en;q=0.8,zh-TW;q=0.6',
      'HTTP_ACCEPT_ENCODING': 'gzip,deflate,sdch',
  }

  POST_ENVIRON_SAMPLE = {
      'wsgi.multiprocess': False,
      'REDIRECT_STATUS': '200',
      'SERVER_SOFTWARE': 'lighttpd/1.4.28',
      'SCRIPT_NAME': '/logparser',
      'REQUEST_METHOD': 'POST',
      'PATH_INFO': '/logparser',
      'SERVER_PROTOCOL': 'HTTP/1.1',
      'QUERY_STRING': '',
      'CONTENT_LENGTH': '0',  # need replace
      'HTTP_USER_AGENT': 'curl/7.22.0 (x86_64-pc-linux-gnu) '
                         'libcurl/7.22.0 OpenSSL/1.0.1 zlib/1.2.3.4 libidn/1.23'
                         'librtmp/2.3',
      'SERVER_NAME': '127.0.0.1',
      'REMOTE_PORT': '46306',
      'wsgi.url_scheme': 'http',
      'SERVER_PORT': '80',
      'SERVER_ADDR': '127.0.0.1',
      'DOCUMENT_ROOT': '/var/www',
      'CONTENT_TYPE': 'multipart/form-data; boundary='
                      '----------------------------00d47a7c8b0d',
      'SCRIPT_FILENAME': '/var/www/logparser',
      'wsgi.input': None,  # need replace
      'HTTP_HOST': '127.0.0.1',
      'wsgi.multithread': True,
      'HTTP_EXPECT': '100-continue',
      'REQUEST_URI': '/logparser',
      'HTTP_ACCEPT': '*/*',
      'wsgi.version': (1, 0),
      'GATEWAY_INTERFACE': 'CGI/1.1',
      'wsgi.run_once': False,
      'wsgi.errors': None,
      'REMOTE_ADDR': '127.0.0.1',
      'HTTP_CONTENT_LENGTH': '0',  # need replace
  }

  YAML_DESCRIPTION_SAMPLE = """
panel_serial: '1234567890'
timestamp: 2014-04-21T13:45:21.123Z
fixture_id: 'henry'
status: PASSED
duration: 10
camera_serial: '54321'
events:
  'result': {'frequency': 100, 'response': 30}
  'test': [123, 456, 789]
vpd:
  'calibration': 'asdfbcd123'
  'gg': '123456'
  'kk': 'True'
rawdata: ['abc.png', 'def.wav']
  """

  def setUp(self):
    self.options = self.emulateOption()
    self.tmpdir = _TMP_COMPRESS_DIR

  def tearDown(self):
    if os.path.exists(_UNITTEST_ROOT):
      shutil.rmtree(_UNITTEST_ROOT)

  def start_response(self, _, data):
    return data

  def createPath(self, path):
    dir_path = os.path.dirname(path)
    if not os.path.exists(dir_path):
      os.makedirs(dir_path)

  def createFile(self, file_path, size):
    self.createPath(file_path)
    buf = '0' * size
    with open(file_path, 'w') as f:
      f.write(buf)

  def emulateOption(self):
    options = {}
    options['tarfile_dir'] = _TAR_FILE_DIR
    options['rawdata_dir'] = _RAW_DATA_DIR
    options['eventlog_dir'] = _EVENT_LOG_DIR
    options['vpd_file'] = _VPD_FILE
    options['camera_file'] = _CAMERA_FILE
    return options

  def emulateCGIField(self, file_name, file_content):
    fs = cgi.FieldStorage()
    fs.name = 'file'
    fs.filename = file_name
    fs.value = file_content
    return fs

  def genUploadFileName(self, log_desc, ext):
    return '%s_%s_%s.%s' % (
        log_desc['fixture_id'],
        log_desc['panel_serial'],
        log_desc['timestamp'].strftime('%Y%m%d%H%M%S%f')[:-3],
        ext)

  def createUploadFile(self, uploadfile_path, config):
    self.createPath(uploadfile_path)
    temp_dir = tempfile.mkdtemp()
    # Prepare files
    file_path = os.path.join(temp_dir, 'description.yaml')
    with open(file_path, 'w') as f:
      f.write(yaml.dump(config))
    if 'rawdata' in config:
      for rawdata in config['rawdata']:
        self.createFile(os.path.join(temp_dir, rawdata), 100)

    # Add to a ZIP file
    with zipfile.ZipFile(uploadfile_path, 'w') as f:
      f.write(file_path, 'description.yaml')
      if 'rawdata' in config:
        for rawdata in config['rawdata']:
          f.write(os.path.join(temp_dir, rawdata), rawdata)

    shutil.rmtree(temp_dir)

  def preparePOSTRequest(self, config):
    file_name = self.genUploadFileName(config, 'zip')
    file_path = os.path.join(self.tmpdir, file_name)
    self.createUploadFile(file_path, config)
    with open(file_path, 'rb') as f:
      file_content = f.read()
    return self.emulateCGIField(file_name, file_content)

  def test_GetWithoutSN(self):
    environ = copy.copy(LogParserUnitTest.GET_ENVIRON_SAMPLE)
    logparser = LogParser(self.options)
    ret = logparser(environ, self.start_response)
    self.assertEqual(ret, ['None'])

    environ['QUERY_STRING'] = 'action=getvpd&abc=123'
    ret = logparser(environ, self.start_response)
    self.assertEqual(ret, ['None'])

  def test_ParseFileName(self):
    def check_FileName(filename, expect_passed, result):
      logparser = LogParser(self.options)
      if expect_passed:
        ret = logparser.ParseFileName(filename)
        self.assertEqual(ret, result)
      else:
        with self.assertRaises(Exception) as e:
          logparser.ParseFileName(filename)
        self.assertEqual(str(e.exception), result)

    name_list = [
        'abc.tgz', 'abc_1234567890.tgz', 'abc_1234567890_1234567890123456.tgz',
        'abc_1234_12345678901234567.tgz', '1234567890_12345678901234567.tgz']
    for name in name_list:
      check_FileName(name, False, 'File name %s does not match pattern.' % name)

    name_list = ['abc_1234567890_12345678901234567.gz',
                 'abc_1234567890_1234567890123456']
    for name in name_list:
      check_FileName(name, False, 'File extension should be tgz or zip.')

    name_list = {
        'abc_1234567890_12345678901234567.tgz': {
            'fixture_id': 'abc',
            'serial_number': '1234567890',
            'time_stamp': '12345678901234567'},
        'def_2345678901_67890123456789012.zip': {
            'fixture_id': 'def',
            'serial_number': '2345678901',
            'time_stamp': '67890123456789012'},
        'hjk_3456789012_98765432109876543.tar': {
            'fixture_id': 'hjk',
            'serial_number': '3456789012',
            'time_stamp': '98765432109876543'},
    }
    for name, value in name_list.iteritems():
      check_FileName(name, True, value)

  def test_DecompressFile(self):
    self.createFile(os.path.join(self.tmpdir, 'abc.png'), 123)
    with zipfile.ZipFile(os.path.join(self.tmpdir,
        'abc_1234567890_12345678901234567.zip'), 'w') as f:
      f.write(os.path.join(self.tmpdir, 'abc.png'), 'abc.png')

    zip_desc = {
        'fixture_id': 'abc',
        'serial_number': '1234567890',
        'time_stamp': '12345678901234567'}
    logparser = LogParser(self.options)
    # Check unsupport format
    with self.assertRaises(Exception) as e:
      ret = logparser.DecompressFile(
          os.path.join(self.tmpdir, 'abc.png'), zip_desc)
    self.assertEqual(str(e.exception), 'Unsupport format.')

    # Check Zip format
    ret = logparser.DecompressFile(os.path.join(self.tmpdir,
        'abc_1234567890_12345678901234567.zip'), zip_desc)
    self.assertEqual(ret, None)

    with tarfile.open(os.path.join(self.tmpdir,
        'def_2345678901_98765432109876543.tar'), 'w') as f:
      f.add(os.path.join(self.tmpdir, 'abc.png'), 'abc.png')

    tar_desc = {
        'fixture_id': 'def',
        'serial_number': '2345678901',
        'time_stamp': '98765432109876'}
    logparser = LogParser(self.options)
    # Check Tar format
    ret = logparser.DecompressFile(os.path.join(self.tmpdir,
        'def_2345678901_98765432109876543.tar'), tar_desc)
    self.assertEqual(ret, None)

    with tarfile.open(os.path.join(self.tmpdir,
        'def_2345678901_98765432109876543.tgz'), 'w:gz') as f:
      f.add(os.path.join(self.tmpdir, 'abc.png'), 'abc.png')

    logparser = LogParser(self.options)
    # Check Tar+GZip format
    ret = logparser.DecompressFile(os.path.join(self.tmpdir,
        'def_2345678901_98765432109876543.tgz'), tar_desc)
    self.assertEqual(ret, None)

  def test_LoadDescription(self):
    def check_Description(config, expect_passed, file_desc):
      logparser = LogParser(self.options)
      file_path = logparser.GetFilePath(file_desc, 'description.yaml')
      self.createPath(file_path)
      with open(file_path, 'w') as f:
        f.write(yaml.dump(config))
      if expect_passed:
        ret = logparser.LoadDescription(file_desc)
      else:
        with self.assertRaises(Exception) as e:
          logparser.LoadDescription(file_desc)
        ret = str(e.exception)
      return ret

    file_desc = {
        'fixture_id': 'abc',
        'serial_number': '2345678901',
        'time_stamp': '12345678901234567'}
    # Check file exist
    logparser = LogParser(self.options)
    with self.assertRaises(Exception) as e:
      ret = logparser.LoadDescription(file_desc)
    self.assertEqual(str(e.exception), 'description.yaml does not exist.')

    # Check mandatory fields
    mandatory_fields = ['panel_serial', 'timestamp', 'fixture_id', 'status',
                        'duration']
    for field in mandatory_fields:
      config = yaml.load(self.YAML_DESCRIPTION_SAMPLE)
      del config[field]
      ret = check_Description(config, False, file_desc)
      self.assertTrue(ret.startswith(
          'Required item %r does not exist' % field))

    # Check panel serial
    config = yaml.load(self.YAML_DESCRIPTION_SAMPLE)
    ret = check_Description(config, False, file_desc)
    self.assertEqual(
        ret, 'Panel serial %r does not match with filename %r.' % (
            config['panel_serial'], file_desc['serial_number']))

    # Check time stamp
    file_desc['serial_number'] = config['panel_serial']
    ret = check_Description(config, False, file_desc)
    t = config['timestamp'].strftime('%Y%m%d%H%M%S%f')[:-3]
    self.assertEqual(
        ret, 'Timestamp %r does not match with filename %r.' % (
            t, file_desc['time_stamp']))

    # Check fixture ID
    file_desc['time_stamp'] = t
    ret = check_Description(config, False, file_desc)
    self.assertEqual(
        ret, 'Fixture ID %r does not match with filename %r.' % (
            config['fixture_id'], file_desc['fixture_id']))

    # Check status
    file_desc['fixture_id'] = config['fixture_id']
    config['status'] = 'UNKNOWN'
    ret = check_Description(config, False, file_desc)
    self.assertEqual(ret, 'Status should be PASSED or FAILED.')

    # Check duration
    config['status'] = 'PASSED'
    config['duration'] = 'abc'
    ret = check_Description(config, False, file_desc)
    self.assertTrue(
        ret.startswith('%r does not match any type' % config['duration']))

    # Check vpd
    config['duration'] = 10.0
    config['vpd']['test'] = ['a', 'b', 'c']
    ret = check_Description(config, False, file_desc)
    self.assertTrue(
        ret.startswith('Type mismatch on %r:' % config['vpd']['test']))

    # Check rawdata
    del config['vpd']['test']
    ret = check_Description(config, False, file_desc)
    self.assertEqual(ret, 'Raw data %s does not exist.' % config['rawdata'][0])

    for rawdata in config['rawdata']:
      file_path = logparser.GetFilePath(file_desc, rawdata)
      self.createFile(file_path, 100)
    ret = check_Description(config, True, file_desc)
    self.assertEqual(ret, config)

  @patch.object(WSGISession, 'GetFile')
  def test_CheckUploadFile(self, mock_GetFile):

    # Check no file or multiple files uploaded
    mock_GetFile.return_value = None
    post_environ = copy.copy(LogParserUnitTest.POST_ENVIRON_SAMPLE)
    logparser = LogParser(self.options)
    ret = logparser(post_environ, self.start_response)
    self.assertEqual(ret, ['FAILED, No file or multiple files uploaded.'])

    # Check exception capture
    mock_GetFile.return_value = self.emulateCGIField('abc.exe', 'content')
    logparser = LogParser(self.options)
    ret = logparser(post_environ, self.start_response)
    self.assertEqual(ret, ['FAILED, File extension should be tgz or zip.'])

    # Check VPD update from two sessions
    config = yaml.load(self.YAML_DESCRIPTION_SAMPLE)
    mock_GetFile.return_value = self.preparePOSTRequest(config)
    logparser = LogParser(self.options)
    ret = logparser(post_environ, self.start_response)
    self.assertEqual(ret[0], 'PASSED')

    config['fixture_id'] = 'abc'
    config['vpd']['addone'] = 'HelloWorld'
    mock_GetFile.return_value = self.preparePOSTRequest(config)
    logparser = LogParser(self.options)
    ret = logparser(post_environ, self.start_response)
    self.assertEqual(ret[0], 'PASSED')

    get_environ = copy.copy(LogParserUnitTest.GET_ENVIRON_SAMPLE)
    get_environ['QUERY_STRING'] = 'action=getvpd&serial=%s' % (
        config['panel_serial'])
    logparser = LogParser(self.options)
    ret = logparser(get_environ, self.start_response)
    self.assertEqual(str(ret[0]), str(config['vpd']))

    # Check camera module is not updated in second session when serial number
    # is the same
    get_environ = copy.copy(LogParserUnitTest.GET_ENVIRON_SAMPLE)
    get_environ['QUERY_STRING'] = 'action=getcamera&serial=%s' % (
        config['panel_serial'])
    logparser = LogParser(self.options)
    ret = logparser(get_environ, self.start_response)
    self.assertEqual(str(ret[0]), str([config['camera_serial']]))

    # Check camera module is updated in third session
    camera_list = [config['camera_serial'], '98765']
    config['camera_serial'] = '98765'
    mock_GetFile.return_value = self.preparePOSTRequest(config)
    logparser = LogParser(self.options)
    ret = logparser(post_environ, self.start_response)
    self.assertEqual(ret[0], 'PASSED')

    get_environ = copy.copy(LogParserUnitTest.GET_ENVIRON_SAMPLE)
    get_environ['QUERY_STRING'] = 'action=getcamera&serial=%s' % (
        config['panel_serial'])
    logparser = LogParser(self.options)
    ret = logparser(get_environ, self.start_response)
    self.assertEqual(str(ret[0]), str(camera_list))

if __name__ == '__main__':
  unittest.main()
