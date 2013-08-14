# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from django.conf.urls import patterns, url
from django.views.generic import RedirectView

import minijack_common  # pylint: disable=W0611
from frontend import views, query_view


urlpatterns = patterns(
  '',
  url(r'^device/(?P<device_id>[^/]*)$', views.GetDeviceView, name='device'),
  url(r'^event/(?P<event_id>[^/]*)$', views.GetEventView, name='event'),
  url(r'^devices$', views.GetDevicesView, name='devices'),
  url(r'^query$', query_view.GetQueryView, name='query'),
  url(r'^hwids$', views.GetHwidsView, name='hwids'),
  url(r'^screenshot/(?P<ip_address>[^/]*)$',
      views.GetScreenshotImage, name='screenshot'),
  url(r'^tests$', views.GetTestsView, name='tests'),
  url(r'^test$', views.GetTestView, name='test'),
  # RedirectView.as_view uses @classonlymethod, a subclass of @classmethod.
  # Pylint doesn't know the @classonlymethod and complains.
  url(r'^$', RedirectView.as_view(url='/devices')), # pylint: disable=E1120
  url(r'^index$', RedirectView.as_view(url='/devices')), # pylint: disable=E1120
  url(r'^build$', RedirectView.as_view(url='/devices')), # pylint: disable=E1120
)
