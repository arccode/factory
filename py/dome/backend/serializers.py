# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import django
from rest_framework import exceptions
from rest_framework import serializers
from rest_framework import validators

from backend.models import Board
from backend.models import Bundle
from backend.models import Resource
from backend.models import TemporaryUploadedFile


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
      model_field=Board._meta.get_field('name'),  # pylint: disable=W0212
      required=False,
      validators=[
          validators.UniqueValidator(queryset=Board.objects.all()),
          django.core.validators.RegexValidator(
              regex=r'^[^/]+$',
              message='Slashes are not allowed in board name')])

  umpire_enabled = serializers.ModelField(
      model_field=(
          Board._meta.get_field('umpire_enabled')),  # pylint: disable=W0212
      required=False)
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

  def create(self, validated_data):
    """Override parent's method."""
    # make sure 'name' exists explicitly
    if 'name' not in validated_data:
      raise exceptions.ValidationError({'name': 'This field is required'})
    name = validated_data.pop('name')
    return Board.CreateOne(name, **validated_data)

  def update(self, instance, validated_data):
    """Override parent's method."""
    return Board.UpdateOne(instance, **validated_data)


class ResourceSerializer(serializers.Serializer):

  type = serializers.CharField()
  version = serializers.CharField(read_only=True)
  hash = serializers.CharField(read_only=True)
  updatable = serializers.BooleanField(read_only=True)
  file_id = serializers.IntegerField(write_only=True)

  def create(self, validated_data):
    board_name = validated_data['board_name']
    if not Board.objects.filter(pk=board_name).exists():
      raise exceptions.ValidationError('Board %s does not exist' % board_name)
    return Resource.CreateOne(board_name,
                              validated_data['type'],
                              validated_data['file_id'])

  def update(self, instance, validated_data):
    """Override parent's method."""
    raise NotImplementedError('Updating a resource is not allowed')


class BundleSerializer(serializers.Serializer):
  """Serialize or deserialize Bundle objects."""

  # TODO(littlecvr): define bundle name rules in a common place
  name = serializers.CharField()
  note = serializers.CharField(required=False)
  active = serializers.NullBooleanField(required=False)
  rules = serializers.DictField(required=False)

  resources = serializers.DictField(read_only=True, child=ResourceSerializer())

  bundle_file_id = serializers.IntegerField(write_only=True, required=False)

  def create(self, validated_data):
    """Override parent's method."""
    validated_data['bundle_name'] = validated_data.pop('name')
    validated_data['bundle_note'] = validated_data.pop('note')
    return Bundle.UploadNew(**validated_data)

  def update(self, instance, validated_data):
    """Override parent's method."""
    data = validated_data.copy()
    board = data.pop('board')
    return BundleModel(board).ModifyOne(**data)
