# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from rest_framework import serializers

from bundles.models import Bundle


class BundleSerializer(serializers.Serializer):
  """Serialize or deserialize Bundle objects."""

  def create(self, validated_data):
    """Override parent's method."""
    raise NotImplementedError
