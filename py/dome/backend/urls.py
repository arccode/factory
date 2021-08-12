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
from django.views.generic import TemplateView
from rest_framework.urlpatterns import format_suffix_patterns
from rest_framework.authtoken import views as drf_views

from backend import common
from backend import views


# TODO(littlecvr): move to common config with umpire.
PROJECT_URL_ARG = r'(?P<project_name>%s)' % common.PROJECT_NAME_RE
BUNDLE_URL_ARG = r'(?P<bundle_name>[^/]+)'  # anything but slash
RESOURCE_URL_ARG = r'(?P<resource_type>[^/]+)'


urlpatterns = [
    url(r'^$', TemplateView.as_view(template_name='index.html')),
    url(r'^auth$', drf_views.obtain_auth_token, name='auth'),
    url(r'^config/(?P<id>\d+)/$', views.ConfigView.as_view()),
    url(r'^files/$', views.FileCollectionView.as_view()),
    url(r'^info$', views.InfoView.as_view()),
    url(r'^projects/$', views.ProjectCollectionView.as_view()),
    url(r'^projects/%s/$' % PROJECT_URL_ARG,
        views.ProjectElementView.as_view()),
    url(r'^projects/%s/bundles/$' % PROJECT_URL_ARG,
        views.BundleCollectionView.as_view()),
    url(r'^projects/%s/bundles/%s/$' % (PROJECT_URL_ARG, BUNDLE_URL_ARG),
        views.BundleElementView.as_view()),
    url(
        r'^projects/%s/bundles/%s/%s$' %
        (PROJECT_URL_ARG, BUNDLE_URL_ARG, RESOURCE_URL_ARG),
        views.ResourceDownloadView.as_view()),
    url(r'^projects/%s/log/compress/$' % PROJECT_URL_ARG,
        views.LogExportView.as_view()),
    url(r'^projects/%s/log/delete/$' % PROJECT_URL_ARG,
        views.LogDeleteView.as_view()),
    url(r'^projects/%s/log/download/$' % PROJECT_URL_ARG,
        views.LogDownloadView.as_view()),
    url(r'^projects/%s/parameters/dirs/$' % PROJECT_URL_ARG,
        views.ParameterDirectoriesView.as_view()),
    url(r'^projects/%s/parameters/files/$' % PROJECT_URL_ARG,
        views.ParameterComponentsView.as_view()),
    url(r'^projects/%s/resources/$' % PROJECT_URL_ARG,
        views.ResourceCollectionView.as_view()),
    url(r'^projects/%s/resources/gc$' % PROJECT_URL_ARG,
        views.ResourceGarbageCollectionView.as_view()),
    url(r'^projects/%s/services/$' % PROJECT_URL_ARG,
        views.ServiceCollectionView.as_view()),
    url(r'^projects/%s/services/schema$' % PROJECT_URL_ARG,
        views.ServiceSchemaView.as_view()),
    url(r'^projects/%s/sync/status/$' % PROJECT_URL_ARG,
        views.SyncStatusView.as_view()),
]

urlpatterns = format_suffix_patterns(urlpatterns)
