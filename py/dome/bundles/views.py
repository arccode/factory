# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from django.http import Http404
from rest_framework import generics, mixins, status
from rest_framework.response import Response
from rest_framework.views import APIView

from bundles.models import Bundle
from bundles.serializers import BundleSerializer


class BundleList(APIView):
  """List all bundles, or upload a new bundle."""

  def get(self, request, board, format=None):
    """Override parent's method."""
    bundle_list = Bundle.ListAll(board)
    serializer = BundleSerializer(board, bundle_list, many=True)
    return Response(serializer.data)

  def post(self, request, board, format=None):
    """Override parent's method."""
    serializer = BundleSerializer(board, data=request.data)
    if serializer.is_valid():
      serializer.save()
      return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
