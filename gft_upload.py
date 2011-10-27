#!/usr/bin/python
#
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
gft_upload: Provides various protocols for uploading report files.
"""

import ftplib
import os
import re
import sys
import time
import urllib
import urlparse

import gft_common
from gft_common import DebugMsg, ErrorDie, ErrorMsg, VerboseMsg, WarningMsg


# Constants
DEFAULT_RETRY_INTERVAL = 60
DEFAULT_RETRY_TIMEOUT = 30


def RetryCommand(callback, message_prefix, interval):
  """Retries running some commands until success.

  Args:
    callback: A callback function to execute specified command, and return
              if the result is success. Callback accepts a param to hold session
              states, including two special values:
                'message' to be logged, and 'abort' to return immediately.
    message_prefix: Prefix string to be displayed.
    interval: Duration (in seconds) between each retry (0 to disable).
  """
  results = {}
  # Currently we do endless retry, if interval is assigned.
  while not callback(results):
    message = results.get('message', 'unknown')
    abort = results.get('abort', False)
    if (not interval) or abort:
      ErrorDie('%s: %s' % (message_prefix, message))
    ErrorMsg('%s: %s' % (message_prefix, message))
    for i in range(interval, 0, -1):
      if i % 10 == 0:
        sys.stderr.write(" Retry in %d seconds...\n" % i)
      time.sleep(1)
  return True


def CustomUpload(source_path, custom_command):
  """Uploads the source file by a customized shell command.

  Args:
    source_path: File to upload.
    custom_command: A shell script command to invoke.
  """
  if not custom_command:
    ErrorDie('CustomUpload: need a shell command for customized uploading.')
  cmd = '%s %s' % (custom_command, source_path)
  DebugMsg('CustomUpload: custom: %s' % cmd)
  if os.system(cmd) != 0:
    ErrorDie('CustomUpload: failed: %s' % cmd)
  VerboseMsg('CustomUpload: successfully invoked command: %s.' % cmd)
  return True


def CurlCommand(curl_command, success_string=None, abort_string=None,
                retry_interval=DEFAULT_RETRY_INTERVAL):
  """Performs arbitrary curl command with retrying.

  Args:
    curl_command: Parameters to be invoked with curl.
    success_string: String to be recognized as "uploaded successfully".
  """
  if not curl_command:
    ErrorDie('CurlCommand: need parameters for curl.')

  cmd = 'curl -s -S %s' % curl_command
  DebugMsg('CurlCommand: %s' % cmd)

  # man curl(1) for EXIT CODES not related to temporary network failure.
  curl_abort_exit_codes = [1, 2, 3, 27, 37, 43, 45, 53, 54, 58, 59, 63]

  def CurlCallback(result):
    (exit_code, stdout, stderr) = (
        gft_common.ShellExecution(cmd, ignore_status=True))
    abort = False
    message = None
    if exit_code == 0:
      if abort_string and stdout.find(abort_string) >= 0:
        message = "Abort: Found abort pattern: %s" % abort_string
      elif (not success_string) or (stdout.find(success_string) >= 0):
        return True
      else:
        message = "Retry: No valid pattern (%s) in response." % success_string
      DebugMsg("CurlCallback: original response: %s" %
               ' '.join(stdout.splitlines()))
    else:
      message = '#%d %s' % (exit_code, stderr if stderr else stdout)
      if exit_code in curl_abort_exit_codes:
        abort = True
    result['abort'] = abort
    result['message'] = message

  RetryCommand(CurlCallback, 'CurlCommand', interval=retry_interval)
  VerboseMsg('CurlCommand: successfully executed: %s' % cmd)
  return True


def CurlUrlUpload(source_path, params, **kargs):
  """Uploads the source file with URL-like protocols by curl.

  Args:
    source_path: File to upload.
    params: Parameters to be invoked with curl.
    retry: Duration (in secnods) for retry.
  """
  return CurlCommand('--ftp-ssl -T "%s" %s' % (source_path, params), **kargs)


def CpfeUpload(source_path, cpfe_url, **kargs):
  """Uploads the source file to ChromeOS Partner Front End site.

  Args:
    source_path: File to upload.
    cpfe_url: URL to CPFE.
    retry: Duration (in secnods) for retry.
  """
  curl_command = '--form "report_file=@%s" %s' % (source_path, cpfe_url)
  CPFE_SUCCESS = '[CPFE UPLOAD: OK]'
  CPFE_ABORT = '[CPFE UPLOAD: INVALID]'
  return CurlCommand(curl_command, success_string=CPFE_SUCCESS,
                     abort_string=CPFE_ABORT, **kargs)


def FtpUpload(source_path, ftp_url, retry_interval=DEFAULT_RETRY_INTERVAL,
              retry_timeout=DEFAULT_RETRY_TIMEOUT):
  """Uploads the source file to a FTP url.

    source_path: File to upload.
    ftp_url: A ftp url in ftp://user@pass:host:port/path format.
    retry_interval: A number in seconds for retry duration. 0 to prevent retry.
    retry_timeout: A number in seconds for connection timeout.

  Raises:
    GFTError: When input url is invalid, or if network issue without retry.
  """
  # scheme: ftp, netloc: user:pass@host:port, path: /...
  url_struct = urlparse.urlparse(ftp_url)
  tokens = re.match('(([^:]*)(:([^@]*))?@)?([^:]*)(:(.*))?', url_struct.netloc)
  userid = tokens.group(2)
  passwd = tokens.group(4)
  host = tokens.group(5)
  port = tokens.group(7)

  # Check and specify default parameters
  if not host:
    ErrorDie('FtpUpload: invalid ftp url: %s' % ftp_url)
  if not port:
    port = ftplib.FTP_PORT
  if not userid:
    userid = 'anonymous'
  if not passwd:
    passwd = ''

  # Parse destination path: According to RFC1738, 3.2.2,
  # Starting with %2F means absolute path, otherwise relative.
  path = urllib.unquote(url_struct.path)
  assert path[0] == '/', 'Unknown FTP URL path.'
  path = path[1:]

  source_name = os.path.split(source_path)[1]
  dest_name = os.path.split(path)[1]
  DebugMsg('source name: %s, dest_name: %s -> %s' % (source_name, path,
                                                     dest_name))
  if source_name and (not dest_name):
    path = os.path.join(path, source_name)

  ftp = ftplib.FTP()
  url = 'ftp://%s:%s@%s:%s/ %s' % (userid, passwd, host, port, path)
  VerboseMsg('FtpUpload: target is %s' % url)

  def FtpCallback(result):
    try:
      ftp.connect(host=host, port=port, timeout=retry_timeout)
      return True
    except Exception, e:
      result['message'] = '%s' % e

  RetryCommand(FtpCallback, 'FtpUpload', interval=retry_interval)

  # Ready for copying files
  DebugMsg('FtpUpload: connected, uploading to %s...' % path)
  ftp.login(user=userid, passwd=passwd)
  with open(source_path, 'rb') as fileobj:
    ftp.storbinary('STOR %s' % path, fileobj)
  DebugMsg('FtpUpload: upload complete.')
  ftp.quit()
  VerboseMsg('FtpUpload: successfully uploaded to %s' % ftp_url)
  return True


def NoneUpload(source_path, **kargs):
  """ Dummy function for bypassing uploads """
  WarningMsg('NoneUpload%s: skipped uploading %s' % (kargs, source_path))
  return True


def Upload(path, method, **kargs):
  """Uploads a file by given method.

  Args:
    path: File path to be uploaded.
    method: A string to specify the method to upload files.
  """
  args = method.split(':', 1)
  method = args[0]
  param = args[1] if len(args) > 1 else None

  if method == 'none':
    return NoneUpload(path, **kargs)
  elif method == 'custom':
    return CustomUpload(path, param, **kargs)
  elif method == 'ftp':
    return FtpUpload(path, 'ftp:' + param, **kargs)
  elif method == 'ftps':
    return CurlUrlUpload(path, '--ftp-ssl-reqd ftp:%s' % param, **kargs)
  elif method == 'cpfe':
    return CpfeUpload(path, param, **kargs)
  else:
    ErrorDie('Upload: unknown method: %s' % method)
  return False


#############################################################################
# Console main entry
@gft_common.GFTConsole
def main():
  gft_common.SetVerboseLevel(True)
  # gft_common.SetDebugLevel(True)
  if len(sys.argv) != 3:
    print "Usage: %s upload_file_path upload_method" % sys.argv[0]
    print """
    Supported values for upload_method:

    none
        Do nothing.

    ftp://userid:passwd@host:port/path
        Upload to a FTP site.

    ftps://userid:passwd@host:port/path [curl_options]
        Upload by FTP-SSL protocol using curl.

    cpfe:cpfe_url [curl_options]
        Upload to Google ChromeOS Partner Front End.

    custom:shell_command
        Invoke a shell command to upload the file.
    """
    sys.exit(1)

  if not Upload(sys.argv[1], sys.argv[2]):
    ErrorDie('ftp_upload: FAILED.')

if __name__ == '__main__':
  main()
