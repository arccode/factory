# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from django.conf.urls import url
from rest_framework.urlpatterns import format_suffix_patterns

from bundles import views


# TODO(littlecvr): move to common config with umpire.
BUNDLE_NAME_REGEXP = r'[^/]+'  # accept anything but slashes


urlpatterns = [
    url(r'^$',
        views.BundleCollectionView.as_view()),
    url(r'^(?P<bundle_name>%s)/resources/$' % BUNDLE_NAME_REGEXP,
        views.BundleResourceView.as_view())]

urlpatterns = format_suffix_patterns(urlpatterns)
