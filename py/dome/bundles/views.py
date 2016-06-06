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
    raise NotImplementedError

  def post(self, request, board, format=None):
    """Override parent's method."""
    raise NotImplementedError
