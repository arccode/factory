# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Dome custom permission, always give permission to client from localhost.
"""

import logging

from rest_framework import permissions as drf_permissions

from backend import common

from cros.factory.utils import net_utils


logger = logging.getLogger('django.%s' % __name__)


class AllowLocalHostOrIsAuthenticated(drf_permissions.IsAuthenticated):

  def has_permission(self, request, view):
    client_ip = request.META['REMOTE_ADDR']

    # allow connection from localhost or docker host
    allowlist = ['127.0.0.1', str(net_utils.GetDockerHostIP())]
    if client_ip in allowlist:
      logger.info('Skip authentication, allow connection from %r', client_ip)
      return True

    if common.IsDomeDevServer():
      logger.info('Skip authentication for dev server')
      return True

    # fallback to authentication
    return super(
        AllowLocalHostOrIsAuthenticated, self).has_permission(request, view)
