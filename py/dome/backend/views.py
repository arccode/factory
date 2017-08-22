# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(littlecvr): return different format specified by "request_format"
#                  variable.

from rest_framework import generics
from rest_framework import mixins
from rest_framework.response import Response
from rest_framework import status

from backend.models import Project
from backend.models import Bundle
from backend.models import DomeConfig
from backend.models import Service
from backend.models import TemporaryUploadedFile
from backend.serializers import ProjectSerializer
from backend.serializers import BundleSerializer
from backend.serializers import ConfigSerializer
from backend.serializers import ResourceSerializer
from backend.serializers import ServiceSerializer
from backend.serializers import UploadedFileSerializer


class ConfigView(mixins.CreateModelMixin,
                 generics.RetrieveUpdateAPIView):

  queryset = DomeConfig.objects.all()
  serializer_class = ConfigSerializer
  lookup_field = 'id'
  lookup_url_kwarg = 'id'

  def put(self, request, *args, **kwargs):
    """Override parent's method."""
    try:
      return self.update(request, *args, **kwargs)
    except Exception:
      return self.create(request, *args, **kwargs)


class FileCollectionView(generics.CreateAPIView):

  queryset = TemporaryUploadedFile.objects.all()
  serializer_class = UploadedFileSerializer


class ServiceSchemaView(generics.ListAPIView):

  serializer_class = ServiceSerializer

  def list(self, request, *args, **kwargs):
    """Override parent's method."""
    return Response(Service.GetServiceSchemata())


class ServiceCollectionView(mixins.UpdateModelMixin,
                            generics.ListAPIView):

  serializer_class = ServiceSerializer

  def list(self, request, *args, **kwargs):
    """Override parent's method."""
    return Response(
        Service.ListAll(self.kwargs['project_name']))

  def put(self, request, project_name, request_format=None):
    """Override parent's method."""
    return Response(Service.Update(project_name, request.data))


class ProjectCollectionView(generics.ListCreateAPIView):

  queryset = Project.objects.all()
  serializer_class = ProjectSerializer


class ProjectElementView(mixins.DestroyModelMixin,
                         generics.UpdateAPIView):

  queryset = Project.objects.all()
  serializer_class = ProjectSerializer
  lookup_field = 'name'
  lookup_url_kwarg = 'project_name'

  def delete(self, request, project_name, request_format=None):
    """Override parent's method."""
    del project_name, request_format  # unused
    return self.destroy(request)

  def perform_destroy(self, instance):
    """Override parent's method."""
    instance.DeleteUmpireContainer().delete()


class BundleCollectionView(generics.ListCreateAPIView):
  """List all bundles, upload a new bundle, or reorder the bundles."""

  serializer_class = BundleSerializer

  def get_queryset(self):
    return Bundle.ListAll(self.kwargs['project_name'])

  def perform_create(self, serializer):
    """Override parent's method."""
    serializer.save(project_name=self.kwargs['project_name'])

  def put(self, request, project_name, request_format=None):
    """Override parent's method."""
    del request_format  # unused
    bundle_list = Bundle.ReorderBundles(project_name, request.data)
    serializer = BundleSerializer(bundle_list, many=True)
    return Response(serializer.data)


class BundleElementView(generics.GenericAPIView):
  """Delete or update a bundle."""

  serializer_class = BundleSerializer

  def delete(self, request, project_name, bundle_name, request_format=None):
    """Override parent's method."""
    del request, request_format  # unused
    Bundle.DeleteOne(project_name, bundle_name)
    return Response(status=status.HTTP_204_NO_CONTENT)

  def put(self, request, project_name, bundle_name, request_format=None):
    """Override parent's method."""
    del request_format  # unused
    bundle = Bundle.ListOne(project_name, bundle_name)

    data = request.data.copy()
    data['name'] = bundle_name
    serializer = self.get_serializer(bundle, data=data)

    serializer.is_valid(raise_exception=True)
    serializer.save(project_name=project_name)

    return Response(serializer.data)


class ResourceCollectionView(generics.CreateAPIView):

  serializer_class = ResourceSerializer

  def perform_create(self, serializer):
    serializer.save(project_name=self.kwargs['project_name'])
