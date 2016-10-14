# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import errno
import os

import mock
import rest_framework.test

from backend import models


class UploadedFileTest(rest_framework.test.APITestCase):

  def setUp(self):
    with open(__file__) as f:
      response = self.client.post('/files/', data={'file': f})
    self.uploaded_file_id = response.json()['id']

  def testWithUploadedFile(self):
    """The normal use case of UploadedFile."""
    with models.UploadedFile(self.uploaded_file_id) as f:
      path = models.UploadedFilePath(f)
      self.assertTrue(os.path.isfile(path))
    self.assertFalse(os.path.exists(path))

  @mock.patch('os.unlink')
  def testWithUploadedFileNoSuchFile(self, unlink):
    """The uploaded file will be removed after used, but it doesn't matter if it
    has already been removed."""
    unlink.side_effect = OSError(errno.ENOENT, 'No such file')

    with models.UploadedFile(self.uploaded_file_id) as f:
      unlink.assert_not_called()
      path = models.UploadedFilePath(f)
    unlink.assert_called_once_with(path)

  @mock.patch('os.unlink')
  def testWithUploadedFileUnlinkRaisesErrorOtherThanENOENT(self, unlink):
    """Test if os.unlink() raises error other than ENOENT."""
    unlink.side_effect = OSError(errno.EACCES, 'Permission denied')

    # This case should never happen actually, but if it happened, we'll just
    # raise.
    with self.assertRaises(OSError):
      with models.UploadedFile(self.uploaded_file_id):
        pass

  @mock.patch('os.rmdir')
  def testWithUploadedFileDirectoryNotEmpty(self, rmdir):
    """The code will try to remove the parent directory of the uploaded file,
    but will fail if it's not empty, which we don't care."""
    rmdir.side_effect = OSError(errno.ENOTEMPTY, 'Directory not empty')

    with models.UploadedFile(self.uploaded_file_id) as f:
      rmdir.assert_not_called()
      path = models.UploadedFilePath(f)
    rmdir.assert_called_once_with(os.path.dirname(path))

  @mock.patch('os.rmdir')
  def testWithUploadedFileRmdirRaisesErrorOtherThanENOTEMPTY(self, rmdir):
    """Test if os.rmdir() raises error other than ENOTEMPTY."""
    rmdir.side_effect = OSError(errno.EACCES, 'Permission denied')

    # This case should never happen actually, but if it happened, we'll just
    # raise.
    with self.assertRaises(OSError):
      with models.UploadedFile(self.uploaded_file_id):
        pass
