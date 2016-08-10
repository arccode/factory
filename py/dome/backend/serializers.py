# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import stat

from rest_framework import serializers

from backend.models import BundleModel


class ResourceSerializer(serializers.Serializer):
  # read only fields
  # TODO(littlecvr): should be choice
  type = serializers.CharField(read_only=True)
  version = serializers.CharField(read_only=True)
  hash = serializers.CharField(read_only=True)
  updatable = serializers.BooleanField(read_only=True)

  # write only fields
  board = serializers.CharField(write_only=True)
  is_inplace_update = serializers.BooleanField(write_only=True)
  src_bundle_name = serializers.CharField(write_only=True)
  dst_bundle_name = serializers.CharField(write_only=True, allow_null=True)
  note = serializers.CharField(write_only=True)
  resource_type = serializers.CharField(write_only=True)
  resource_file = serializers.FileField(write_only=True, use_url=False)

  def update(self, instance, validated_data):
    old_path = validated_data['resource_file'].temporary_file_path()
    new_path = os.path.join(os.path.dirname(old_path),
                            validated_data['resource_file'].name)

    # Rename the file to its original file name before updating. Umpire copies
    # the file into its resources folder without renaming the incoming file
    # (though it appends version and hash). If we don't do this, the umpire
    # resources folder will soon be filled with many
    # 'tmp.XXXXXX#{version}#{hash}', and it'll be hard to tell what the files
    # actually are. Also, making a copy is not acceptable, because resource
    # files can be very large.
    # TODO(littlecvr): make Umpire support renaming when updating.
    try:
      os.rename(old_path, new_path)

      # make sure it's readable to umpire
      os.chmod(new_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
      new_validated_data = validated_data.copy()
      new_validated_data.pop('resource_file')
      new_validated_data['resource_file_path'] = new_path

      board = new_validated_data.pop('board')
      inplace_update = new_validated_data.pop('is_inplace_update')
      if inplace_update:
        new_validated_data['dst_bundle_name'] = None
      resource = BundleModel(board).UpdateResource(**new_validated_data)
    finally:
      os.rename(new_path, old_path)

    return resource


class BundleSerializer(serializers.Serializer):
  """Serialize or deserialize Bundle objects."""
  board = serializers.CharField(write_only=True)
  # TODO(littlecvr): define bundle name rules in a common place
  name = serializers.CharField()
  note = serializers.CharField()
  # TODO(littlecvr): implement active/inactive toggle in the future
  active = serializers.BooleanField(read_only=True)
  resources = serializers.DictField(read_only=True, child=ResourceSerializer())

  bundle_file = serializers.FileField(write_only=True, use_url=False)

  def create(self, validated_data):
    """Override parent's method."""
    # file_utils rely on file name suffix to determine how to decompress, so we
    # need to rename the file correctly.
    old_path = validated_data['bundle_file'].temporary_file_path()
    new_path = old_path + '.tar.bz2'
    try:
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

      board = new_validated_data.pop('board')
      bundle = BundleModel(board).UploadNew(**new_validated_data)
    finally:
      # Rename back so django will automatically remove the temporary file.
      os.rename(new_path, old_path)

    return bundle
