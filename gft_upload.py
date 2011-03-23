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


def FtpUpload(source_path, ftp_url, retry=0, timeout=10):
  """Uploads the source file to a FTP url.

  Args:
    source_path: File to upload.
    ftp_url: A ftp url in ftp://user@pass:host:port/path format.
    retry: A number in seconds for retry duration. 0 to prevent retry.
    timeout: A number in seconds for connection timeout.

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
  VerboseMsg('FtpUpload: target is ftp://%s:%s@%s:%s/ %s' %
             (userid, passwd, host, port, path))
  while True:
    try:
      ftp.connect(host=host, port=port, timeout=timeout)
      break
    except Exception, e:
      if not retry:
        ErrorDie('Cannot connect to: %s:%s [timeout=%s]' %
                 (host, port, timeout))
      ErrorMsg("\n FTP ERROR: %s" % e)
      for i in range(retry, 0, -1):
        if i % 10 == 0:
          WarningMsg(" Retry FTP after %d seconds ( %s )..." % (i, ftp_url))
        time.sleep(1)

  # Ready for copying files
  DebugMsg('FtpUpload: connected, uploading to %s...' % path)
  ftp.login(user=userid, passwd=passwd)
  with open(source_path, 'rb') as fileobj:
    ftp.storbinary('STOR %s' % path, fileobj)
  DebugMsg('FtpUpload: upload complete.')
  ftp.quit()
  VerboseMsg('FtpUpload: successfully uploaded to %s' % ftp_url)
  return True


def NoneUpload(source_path):
  """ Dummy function for bypassing uploads """
  WarningMsg('NoneUpload: skipped uploading %s' % source_path)
  return True


def Upload(path, method, network_retry=60):
  """Uploads a file by given method.

  Args:
    path: File path to be uploaded.
    method: A string to specify the method to upload files.
    network_retry: A number in seconds for retrying network connection.
  """
  args = method.split(':', 1)
  method = args[0]
  param = args[1] if len(args) > 1 else None

  if method == 'none':
    return NoneUpload(path)
  elif method == 'custom':
    return CustomUpload(path, param)
  elif method == 'ftp':
    return FtpUpload(path, 'ftp:' + param, retry=network_retry)
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
        Upload to a ftp site

    custom:shell_command
        Invoke a shell command to upload the file.
    """
    sys.exit(1)

  if not Upload(sys.argv[1], sys.argv[2]):
    ErrorDie('ftp_upload: FAILED.')

if __name__ == '__main__':
  main()
