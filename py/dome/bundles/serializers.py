# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import stat

from rest_framework import serializers

from bundles.models import Bundle


class BundleSerializer(serializers.Serializer):
  """Serialize or deserialize Bundle objects."""
  name = serializers.CharField(allow_blank=False, max_length=200)
  note = serializers.CharField()
  bundle_file = serializers.FileField(write_only=True, use_url=False)

  def __init__(self, board, *args, **kwargs):
    self.board = board
    super(BundleSerializer, self).__init__(*args, **kwargs)

  def __new__(cls, dummy_board, *args, **kwargs):
    return super(BundleSerializer, cls).__new__(cls, *args, **kwargs)

  def create(self, validated_data):
    """Override parent's method."""
    # file_utils rely on file name suffix to determine how to decompress, so we
    # need to rename the file correctly.
    old_path = validated_data['bundle_file'].temporary_file_path()
    new_path = old_path + '.tar.bz2'
    os.rename(old_path, new_path)
    # Umpire service is run by other user, need to give it permission to read.
    os.chmod(new_path, os.stat(new_path)[stat.ST_MODE] | stat.S_IROTH)

    # We don't take advantage of django's FileField in model (which will
    # automatically save the UploadedFile into file system and write information
    # into the database), so we need to handle the file on our own.
    new_validated_data = validated_data.copy()
    # convert 'bundle_file' to 'file_path'
    new_validated_data.pop('bundle_file');
    new_validated_data['file_path'] = new_path

    bundle = Bundle.UploadNew(self.board, **new_validated_data)

    # Rename back so django will automatically remove the temporary file.
    os.rename(new_path, old_path)

    return bundle
