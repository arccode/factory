# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from rest_framework import serializers

from backend.models import Board, BundleModel, TemporaryUploadedFile


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
  umpire_factory_toolkit_file_id = serializers.IntegerField(
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
  resource_file_id = serializers.IntegerField(write_only=True)

  def create(self, validated_data):
    """Override parent's method."""
    raise NotImplementedError('Creating a resource is not allowed')

  def update(self, instance, validated_data):
    """Override parent's method."""
    data = validated_data.copy()

    board = data.pop('board')

    inplace_update = data.pop('is_inplace_update')
    if inplace_update:
      data['dst_bundle_name'] = None

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

  bundle_file_id = serializers.IntegerField(write_only=True, required=False)

  def create(self, validated_data):
    """Override parent's method."""
    data = validated_data.copy()
    board = data.pop('board')
    data.pop('rules', None)
    return BundleModel(board).UploadNew(**data)

  def update(self, instance, validated_data):
    """Override parent's method."""
    data = validated_data.copy()
    board = data.pop('board')
    return BundleModel(board).ModifyOne(**data)
