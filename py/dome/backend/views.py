# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# TODO(littlecvr): return different format specified by "request_format"
#                  variable.

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.models import Board, BundleModel
from backend.serializers import (
    BoardSerializer, BundleSerializer, ResourceSerializer)


class BoardCollectionView(generics.ListCreateAPIView):

  serializer_class = BoardSerializer

  def get_queryset(self):
    """Override parent's method."""
    return Board.ListAll()


class BoardElementView(APIView):

  def get_queryset(self):
    """Override parent's method."""
    return Board.ListAll()

  def delete(self, unused_request, board,
             request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    try:
      Board.DeleteOne(board)
      return Response(status=status.HTTP_204_NO_CONTENT)
    except Board.DoesNotExist:
      return Response(status=status.HTTP_404_NOT_FOUND)


class BundleCollectionView(APIView):
  """List all bundles, or upload a new bundle."""

  def get(self, unused_request, board,
          request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    bundle_list = BundleModel(board).ListAll()
    serializer = BundleSerializer(bundle_list, many=True)
    return Response(serializer.data)

  def post(self, request, board,
           request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    data = request.data.copy()
    data['board'] = board
    serializer = BundleSerializer(data=data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

  def put(self, request, board,
          request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    bundle_list = BundleModel(board).ReorderBundles(request.data)
    serializer = BundleSerializer(bundle_list, many=True)
    return Response(serializer.data)

class BundleView(APIView):
  """Delete or update a bundle."""

  def delete(self, unused_request, board, bundle,
             request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    BundleModel(board).DeleteOne(bundle)
    return Response(status=status.HTTP_204_NO_CONTENT)

  def put(self, request, board, bundle,
          request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    bundle = BundleModel(board).ListOne(bundle)
    data = request.data.copy()
    data['board'] = board
    serializer = BundleSerializer(bundle, data=data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BundleResourceView(APIView):
  """Update resource in a particular bundle."""

  def put(self, request, board,
          request_format=None):  # pylint: disable=unused-argument
    """Override parent's method."""
    # TODO(littlecvr): should create bundle instance before creating serializer
    serializer = ResourceSerializer(board, data=request.data)
    if serializer.is_valid():
      BundleModel(board).ListOne(serializer.validated_data['src_bundle_name'])
      serializer.save()
      return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
