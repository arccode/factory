# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import contextlib
import errno
import os
import shutil
import stat
import tempfile

from rest_framework import serializers

from backend.models import (
    Board, BundleModel, TemporaryUploadedFile, UMPIRE_BASE_DIR)


@contextlib.contextmanager
def UmpireAccessibleFile(board, uploaded_file):
  """Make a file uploaded from Dome accessible by a specific Umpire container.

  This function:
  1. creates a temp folder in UMPIRE_BASE_DIR
  2. copies the uploaded file to the temp folder
  3. runs chmod on the folder and file to make sure Umpire is readable
  4. remove the temp folder at the end

  Note that we need to rename the file to its original basename. Umpire copies
  the file into its resources folder without renaming the incoming file (though
  it appends version and hash). If we don't do this, the umpire resources folder
  will soon be filled with many 'tmp.XXXXXX#{version}#{hash}', and it'll be hard
  to tell what the files actually are. Also, due to the way Umpire Docker is
  designed, it's not possible to move the file instead of copy now.

  TODO(littlecvr): make Umpire support renaming when updating.
  TODO(b/31417203): provide an argument to choose from moving file instead of
                    copying (after the issue has been solved).

  Args:
    board: name of the board (used to construct Umpire container's name).
    uploaded_file: TemporaryUploadedFile instance from django.
  """
  container_name = Board.GetUmpireContainerName(board)

  try:
    # TODO(b/31417203): use volume container or named volume instead of
    #                   UMPIRE_BASE_DIR.
    temp_dir = tempfile.mkdtemp(dir='%s/%s' % (UMPIRE_BASE_DIR, container_name))
    new_path = os.path.join(temp_dir, uploaded_file.name)
    shutil.copy(uploaded_file.temporary_file_path(), new_path)

    # make sure they're readable to umpire
    os.chmod(temp_dir, stat.S_IRWXU | stat.S_IROTH | stat.S_IXOTH)
    os.chmod(new_path, stat.S_IRWXU | stat.S_IROTH | stat.S_IXOTH)

    # The temp folder:
    #   in Dome:   ${UMPIRE_BASE_DIR}/${container_name}/${temp_dir}
    #   in Umpire: ${UMPIRE_BASE_DIR}/${temp_dir}
    # so need to remove "${container_name}/"
    yield new_path.replace('%s/' % container_name, '')
  finally:
    # TODO(b/31415816): should not need to close file ourselves here.
    uploaded_file.close()

    try:
      shutil.rmtree(temp_dir)
    except OSError as e:
      # doesn't matter if the folder is removed already, otherwise, raise
      if e.errno != errno.ENOENT:
        raise


class UploadedFileSerializer(serializers.ModelSerializer):

  class Meta(object):

    model = TemporaryUploadedFile

  def create(self, validated_data):
    """Override parent's method."""
    try:
      return super(UploadedFileSerializer, self).create(validated_data)
    finally:
      # TODO(b/31415816): should not close the file ourselves. This function can
      #                   be entirely removed after the issue has been solved
      #                   (just use the parent's version).
      validated_data['file'].close()


class BoardSerializer(serializers.Serializer):

  name = serializers.ModelField(
      model_field=Board._meta.get_field('name'))  # pylint: disable=W0212

  # cannot use ModelField here, django won't convert 'false' to boolean
  umpire_enabled = serializers.BooleanField()
  umpire_host = serializers.ModelField(
      model_field=Board._meta.get_field('umpire_host'),  # pylint: disable=W0212
      required=False)
  umpire_port = serializers.ModelField(
      model_field=Board._meta.get_field('umpire_port'),  # pylint: disable=W0212
      required=False)

  # True means the user is trying to add an existing Umpire container; False
  # means the user asked to create a new one
  umpire_add_existing_one = serializers.BooleanField(
      write_only=True, required=False)

  # TODO(b/31281536): remove this once the issue has been solved
  umpire_factory_toolkit_file = serializers.FileField(
      write_only=True, required=False)

  def create(self, validated_data):
    """Override parent's method."""
    name = validated_data.pop('name')
    return Board.CreateOne(name, **validated_data)

  def update(self, instance, validated_data):
    """Override parent's method."""
    return Board.UpdateOne(instance, **validated_data)


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

  def create(self, validated_data):
    """Override parent's method."""
    raise NotImplementedError('Creating a resource is not allowed')

  def update(self, instance, validated_data):
    """Override parent's method."""
    data = validated_data.copy()

    board = data.pop('board')
    resource_file = data.pop('resource_file')

    inplace_update = data.pop('is_inplace_update')
    if inplace_update:
      data['dst_bundle_name'] = None

    with UmpireAccessibleFile(board, resource_file) as path:
      data['resource_file_path'] = path
      return BundleModel(board).UpdateResource(**data)



class BundleSerializer(serializers.Serializer):
  """Serialize or deserialize Bundle objects."""

  board = serializers.CharField(write_only=True)
  # TODO(littlecvr): define bundle name rules in a common place
  name = serializers.CharField()
  note = serializers.CharField(required=False)
  active = serializers.NullBooleanField(required=False)
  rules = serializers.DictField(required=False)

  resources = serializers.DictField(read_only=True, child=ResourceSerializer())

  bundle_file = serializers.FileField(write_only=True, use_url=False,
                                      required=False)

  def create(self, validated_data):
    """Override parent's method."""
    data = validated_data.copy()
    board = data.pop('board')
    data.pop('rules', None)
    bundle_file = data.pop('bundle_file')
    with UmpireAccessibleFile(board, bundle_file) as path:
      data['file_path'] = path
      return BundleModel(board).UploadNew(**data)

  def update(self, instance, validated_data):
    """Override parent's method."""
    data = validated_data.copy()
    board = data.pop('board')
    return BundleModel(board).ModifyOne(**data)
