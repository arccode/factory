# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(littlecvr): return different format specified by "request_format"
#                  variable.

import os

from django.http import StreamingHttpResponse
from rest_framework import generics
from rest_framework import mixins
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework import status
from rest_framework import views

from backend import common
from backend.models import Bundle
from backend.models import DomeConfig
from backend.models import Log
from backend.models import ParameterComponent
from backend.models import ParameterDirectory
from backend.models import Project
from backend.models import Resource
from backend.models import Service
from backend.models import TemporaryUploadedFile
from backend.models import GetUmpireSyncStatus
from backend.serializers import BundleSerializer
from backend.serializers import ConfigSerializer
from backend.serializers import LogDeleteSerializer
from backend.serializers import LogDownloadSerializer
from backend.serializers import LogSerializer
from backend.serializers import ParameterComponentSerializer
from backend.serializers import ParameterDirectorySerializer
from backend.serializers import ProjectSerializer
from backend.serializers import ResourceSerializer
from backend.serializers import ServiceSerializer
from backend.serializers import UploadedFileSerializer


class InfoView(views.APIView):
  """View to get general info about Dome."""
  permission_classes = (permissions.AllowAny,)

  def get(self, request):
    del request  # Unused.
    docker_image_githash = os.environ.get('DOCKER_IMAGE_GITHASH', '')
    docker_image_islocal = os.environ.get('DOCKER_IMAGE_ISLOCAL', '1')
    # The DOCKER_IMAGE_ISLOCAL is a string '0' or '1', transform it back to
    # boolean.
    docker_image_islocal = bool(int(docker_image_islocal))
    docker_image_timestamp = os.environ.get('DOCKER_IMAGE_TIMESTAMP', '')
    return Response({
        'docker_image_githash': docker_image_githash,
        'docker_image_islocal': docker_image_islocal,
        'docker_image_timestamp': docker_image_timestamp,
        'is_dev_server': common.IsDomeDevServer()
    })


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
    del request, args, kwargs  # unused
    return Response(Service.GetServiceSchemata())


class ServiceCollectionView(mixins.UpdateModelMixin,
                            generics.ListAPIView):

  serializer_class = ServiceSerializer

  def list(self, request, *args, **kwargs):
    """Override parent's method."""
    del request, args, kwargs  # unused
    return Response(Service.ListAll(self.kwargs['project_name']))

  def put(self, request, project_name, request_format=None):
    """Override parent's method."""
    del request_format  # unused
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


class LogDownloadView(views.APIView):

  def get(self, request, *args, **kwargs):
    del args, kwargs
    serializer = LogDownloadSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    download_params = serializer.data
    log_file = Log.Download(download_params)
    return StreamingHttpResponse(log_file,
                                 content_type='application/octet-stream')


class LogExportView(views.APIView):

  def get(self, request, *args, **kwargs):
    del args
    serializer = LogSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    compress_params = serializer.data
    response = Log.Export(kwargs['project_name'], compress_params)
    return Response(response)


class LogDeleteView(views.APIView):

  def delete(self, request, *args, **kwargs):
    del args, kwargs
    serializer = LogDeleteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    discard_params = serializer.data
    response = Log.Delete(discard_params['tmp_dir'])
    return Response(response)


class ResourceCollectionView(generics.CreateAPIView):

  serializer_class = ResourceSerializer

  def perform_create(self, serializer):
    serializer.save(project_name=self.kwargs['project_name'])


class ResourceGarbageCollectionView(views.APIView):

  def post(self, request, *args, **kwargs):
    del request, args  # unused
    return Response(Resource.GarbageCollection(kwargs['project_name']))

class ParameterComponentsView(generics.ListCreateAPIView):

  serializer_class = ParameterComponentSerializer

  def get_queryset(self):
    return ParameterComponent.ListAll(self.kwargs['project_name'])

  def perform_create(self, serializer):
    serializer.save(project_name=self.kwargs['project_name'])


class ParameterDirectoriesView(generics.ListCreateAPIView):

  serializer_class = ParameterDirectorySerializer

  def get_queryset(self):
    return ParameterDirectory.ListAll(self.kwargs['project_name'])

  def perform_create(self, serializer):
    serializer.save(project_name=self.kwargs['project_name'])


class ResourceDownloadView(views.APIView):

  def get(self, request, *args, **kwargs):
    del request, args
    resource_file = Resource.Download(kwargs['project_name'],
                                      kwargs['bundle_name'],
                                      kwargs['resource_type'])
    return StreamingHttpResponse(resource_file,
                                 content_type='application/octet-stream')


class SyncStatusView(views.APIView):
  permission_classes = (permissions.AllowAny, )

  def get(self, request, *args, **kwargs):
    del request, args  # Unused.
    return Response(GetUmpireSyncStatus(kwargs['project_name']))
