# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from django.conf.urls.defaults import patterns, url
from django.conf.urls.static import static

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.frontend import settings, views


urlpatterns = patterns('',
  url(r'^$', views.GetIndexView, name='index'),
) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
