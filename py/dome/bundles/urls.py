# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from django.conf.urls import url
from rest_framework.urlpatterns import format_suffix_patterns

from bundles import views


urlpatterns = [
    url(r'^$', views.BundleList.as_view())]

urlpatterns = format_suffix_patterns(urlpatterns)
