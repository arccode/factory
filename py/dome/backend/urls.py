# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""dome URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.9/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""

from django.conf.urls import url
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.views.generic import TemplateView
from rest_framework.urlpatterns import format_suffix_patterns

from backend import views


# TODO(littlecvr): move to common config with umpire.
BOARD_URL_ARG = r'(?P<board_name>[_a-zA-Z]+)'
BUNDLE_URL_ARG = r'(?P<bundle_name>[^/]+)'  # anything but slash


urlpatterns = [
    url(r'^$',
        TemplateView.as_view(template_name='index.html')),
    url(r'^files/$',
        views.FileCollectionView.as_view()),
    url(r'^boards/$',
        views.BoardCollectionView.as_view()),
    url(r'^boards/%s/$' % BOARD_URL_ARG,
        views.BoardElementView.as_view()),
    url(r'^boards/%s/bundles/$' % BOARD_URL_ARG,
        views.BundleCollectionView.as_view()),
    url(r'^boards/%s/bundles/%s/$' % (BOARD_URL_ARG, BUNDLE_URL_ARG),
        views.BundleView.as_view()),
    url(r'^boards/%s/resources/$' % BOARD_URL_ARG,
        views.ResourceCollectionView.as_view())]

urlpatterns = format_suffix_patterns(urlpatterns)
urlpatterns += staticfiles_urlpatterns()
