# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import django
from rest_framework import exceptions  # pylint: disable=wrong-import-order
from rest_framework import serializers
from rest_framework import validators

from backend import common
from backend.models import Bundle
from backend.models import DomeConfig
from backend.models import ParameterComponent
from backend.models import ParameterDirectory
from backend.models import Project
from backend.models import Resource
from backend.models import Service
from backend.models import TemporaryUploadedFile


class ConfigSerializer(serializers.ModelSerializer):

  class Meta:
    model = DomeConfig
    fields = '__all__'

  def create(self, validated_data):
    """Override parent's method."""
    config_count = DomeConfig.objects.all().count()
    if config_count > 0:
      raise exceptions.ValidationError('There should be only one Config')
    instance = super(ConfigSerializer, self).create(validated_data)
    return DomeConfig.UpdateConfig(instance, **validated_data)

  def update(self, instance, validated_data):
    """Override parent's method."""
    return DomeConfig.UpdateConfig(instance, **validated_data)


class UploadedFileSerializer(serializers.ModelSerializer):

  class Meta:
    model = TemporaryUploadedFile
    fields = '__all__'


class ProjectSerializer(serializers.ModelSerializer):

  name = serializers.ModelField(
      model_field=Project._meta.get_field('name'),  # pylint: disable=W0212
      required=False,
      validators=[
          validators.UniqueValidator(queryset=Project.objects.all()),
          django.core.validators.RegexValidator(
              regex=r'^%s$' % common.PROJECT_NAME_RE,
              message='Invalid project name')])

  has_existing_umpire = serializers.ReadOnlyField()

  class Meta:
    model = Project
    fields = '__all__'
    read_only_fields = ('umpire_version', )

  def create(self, validated_data):
    """Override parent's method."""
    # make sure 'name' exists explicitly
    if 'name' not in validated_data:
      raise exceptions.ValidationError({'name': 'This field is required'})
    name = validated_data.pop('name')
    return Project.CreateOne(name, **validated_data)

  def update(self, instance, validated_data):
    """Override parent's method."""
    return Project.UpdateOne(instance, **validated_data)


class ResourceSerializer(serializers.Serializer):

  type = serializers.CharField()
  version = serializers.CharField(read_only=True)
  file_id = serializers.IntegerField(write_only=True)

  def create(self, validated_data):
    project_name = validated_data['project_name']
    if not Project.objects.filter(pk=project_name).exists():
      raise exceptions.ValidationError(
          'Project %s does not exist' % project_name)
    return Resource.CreateOne(project_name,
                              validated_data['type'],
                              validated_data['file_id'])

  def update(self, instance, validated_data):
    """Override parent's method."""
    raise NotImplementedError('Updating a resource is not allowed')


class BundleSerializer(serializers.Serializer):
  """Serialize or deserialize Bundle objects."""

  # TODO(littlecvr): define bundle name rules in a common place
  name = serializers.CharField()
  note = serializers.CharField(required=False, allow_blank=True)
  active = serializers.NullBooleanField(required=False)
  rules = serializers.DictField(required=False)
  resources = serializers.DictField(required=False, child=ResourceSerializer())

  new_name = serializers.CharField(write_only=True, required=False)
  bundle_file_id = serializers.IntegerField(write_only=True, required=False)

  def create(self, validated_data):
    """Override parent's method."""
    validated_data['bundle_name'] = validated_data.pop('name')
    validated_data['bundle_note'] = validated_data.pop('note')
    return Bundle.UploadNew(**validated_data)

  def update(self, instance, validated_data):
    """Override parent's method."""
    project_name = validated_data.pop('project_name')
    bundle_name = instance.name
    data = {'dst_bundle_name': validated_data.pop('new_name', None),
            'note': validated_data.pop('note', None),
            'active': validated_data.pop('active', None),
            'resources': validated_data.pop('resources', None)}
    return Bundle.ModifyOne(project_name, bundle_name, **data)


class ServiceSerializer(serializers.ModelSerializer):

  class Meta:
    model = Service
    fields = '__all__'


class ParameterComponentSerializer(serializers.Serializer):

  id = serializers.IntegerField(allow_null=True)
  dir_id = serializers.IntegerField(required=False, allow_null=True)
  name = serializers.CharField()
  using_ver = serializers.IntegerField(required=False)
  revisions = serializers.ListField(required=False,
                                    child=serializers.CharField())
  file_id = serializers.IntegerField(required=False, write_only=True)

  def create(self, validated_data):
    """Override parent's method."""
    project_name = validated_data.pop('project_name')
    data = {'id': validated_data.pop('id'),
            'dir_id': validated_data.pop('dir_id', None),
            'name': validated_data.pop('name'),
            'using_ver': validated_data.pop('using_ver', None),
            'file_id': validated_data.pop('file_id', None)}
    return ParameterComponent.CreateOne(project_name, **data)


class ParameterDirectorySerializer(serializers.Serializer):

  id = serializers.IntegerField(required=False)
  parent_id = serializers.IntegerField(required=False, allow_null=True)
  name = serializers.CharField()

  def create(self, validated_data):
    """Override parent's method."""
    project_name = validated_data.pop('project_name')
    data = {'id': validated_data.pop('id', None),
            'parent_id': validated_data.pop('parent_id', None),
            'name': validated_data.pop('name')}
    return ParameterDirectory.CreateOne(project_name, **data)


class LogSerializer(serializers.Serializer):

  log_type = serializers.CharField()
  size = serializers.IntegerField()
  size_unit = serializers.RegexField(regex='^(M|G)B$')
  start_date = serializers.DateField(format='%Y%m%d')
  end_date = serializers.DateField(format='%Y%m%d')


class LogDownloadSerializer(serializers.Serializer):

  log_file = serializers.CharField()
  tmp_dir = serializers.CharField()


class LogDeleteSerializer(serializers.Serializer):

  tmp_dir = serializers.CharField()
