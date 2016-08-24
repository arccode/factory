# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from django.http import Http404
from rest_framework import generics, mixins, status
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.models import BoardModel, BundleModel
from backend.serializers import (
    BoardSerializer, BundleSerializer, ResourceSerializer)


class BoardCollectionView(generics.ListCreateAPIView):
  queryset = BoardModel.objects.all()
  serializer_class = BoardSerializer


class BundleCollectionView(APIView):
  """List all bundles, or upload a new bundle."""

  def get(self, request, board, format=None):
    """Override parent's method."""
    bundle_list = BundleModel(board).ListAll()
    serializer = BundleSerializer(bundle_list, many=True)
    return Response(serializer.data)

  def post(self, request, board, format=None):
    """Override parent's method."""
    serializer = BundleSerializer(data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class BundleView(APIView):
  """Update a bundle."""

  def put(self, request, board, bundle, format=None):
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

  def put(self, request, board, format=None):
    """Override parent's method."""
    # TODO(littlecvr): should create bundle instance before creating serializer
    serializer = ResourceSerializer(board, data=request.data)
    if serializer.is_valid():
      bundle = BundleModel(board).ListOne(
          serializer.validated_data['src_bundle_name'])
      serializer.save()
      return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
