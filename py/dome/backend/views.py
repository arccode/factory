# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(littlecvr): return different format specified by "request_format"
#                  variable.

from rest_framework import generics
from rest_framework import mixins
from rest_framework.response import Response
from rest_framework import status
from rest_framework import views

from backend.models import Board
from backend.models import BundleModel
from backend.models import TemporaryUploadedFile
from backend.serializers import BoardSerializer
from backend.serializers import BundleSerializer
from backend.serializers import ResourceSerializer
from backend.serializers import UploadedFileSerializer


class FileCollectionView(generics.CreateAPIView):

  queryset = TemporaryUploadedFile.objects.all()
  serializer_class = UploadedFileSerializer


class BoardCollectionView(generics.ListCreateAPIView):

  queryset = Board.objects.all()
  serializer_class = BoardSerializer


class BoardElementView(mixins.DestroyModelMixin,
                       generics.UpdateAPIView):

  queryset = Board.objects.all()
  serializer_class = BoardSerializer
  lookup_field = 'name'
  lookup_url_kwarg = 'board_name'

  def delete(self, request,
             board_name,  # pylint: disable=unused-argument
             request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    return self.destroy(request)

  def perform_destroy(self, instance):
    """Override parent's method."""
    instance.DeleteUmpireContainer().delete()


class BundleCollectionView(views.APIView):
  """List all bundles, or upload a new bundle."""

  def get(self, unused_request, board_name,
          request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    bundle_list = BundleModel(board_name).ListAll()
    serializer = BundleSerializer(bundle_list, many=True)
    return Response(serializer.data)

  def post(self, request, board_name,
           request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    data = request.data.copy()
    data['board'] = board_name
    serializer = BundleSerializer(data=data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

  def put(self, request, board_name,
          request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    bundle_list = BundleModel(board_name).ReorderBundles(request.data)
    serializer = BundleSerializer(bundle_list, many=True)
    return Response(serializer.data)

class BundleView(views.APIView):
  """Delete or update a bundle."""

  def delete(self, unused_request, board_name, bundle_name,
             request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    BundleModel(board_name).DeleteOne(bundle_name)
    return Response(status=status.HTTP_204_NO_CONTENT)

  def put(self, request, board_name, bundle_name,
          request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    bundle = BundleModel(board_name).ListOne(bundle_name)
    data = request.data.copy()
    data['board'] = board_name
    serializer = BundleSerializer(bundle, data=data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BundleResourceView(views.APIView):
  """Update resource in a particular bundle."""

  def put(self, request, board_name,
          request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    # TODO(littlecvr): should create bundle instance before creating serializer
    serializer = ResourceSerializer(board_name, data=request.data)
    if serializer.is_valid():
      serializer.save()
      # TODO(littlecvr): return only the resource updated. The front-end needs
      #                  the full bundle data to do post processing now, say we
      #                  updated device_factory_toolkit, but in fact
      #                  server_factory_toolkit will also be affected. To solve
      #                  this, we'll need an alias shared between Umpire, Dome
      #                  back-end, and front-end specifying which resources are
      #                  correlated.
      bundle = BundleModel(board_name).ListOne(
          serializer.validated_data['dst_bundle_name'] or
          serializer.validated_data['src_bundle_name'])
      return Response(BundleSerializer(bundle).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
