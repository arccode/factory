# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Umpire resource map web application.

The class handles
  'http://umpire_address:umpire_port/webapps/resourcemap' HTTP GET.
"""

import logging

from cros.factory.umpire.server.web import wsgi


PATH_INFO = '/webapps/resourcemap'


def GetResourceMap(env):
  """Gets resource map for the DUT.

  It is used for twisted to call when receiving "GET /webapps/resourcemap"
  request.

  Args:
    env: an UmpireEnv object.

  Returns:
    String for response text.
  """
  result = []

  bundle = env.config.GetActiveBundle()

  # TODO(hungte) Remove __token__ and shop_floor_handler when most DUTs have
  # finished migration.
  result = ['id: %s' % bundle['id'],
            'note: %s' % bundle['note'],
            '__token__: 00000001',
            'shop_floor_handler: /umpire',
            'payloads: %s' % bundle['payloads']]

  # Only add multicast resource when the multicast service is active.
  if env.config['services'].get('multicast', {}).get('active', False):
    result.append('multicast: %s' % env.config['multicast'])

  return ''.join('%s\n' % s for s in result)


class ResourceMapApp(wsgi.WebApp):
  """ResourceMap web application class.

  Args:
    env: UmpireEnv object.
  """

  def __init__(self, env):
    self._env = env

  def Handle(self, session):
    """Gets resource map from DUT info and return text/plain result."""
    logging.debug('resourcemap app: %s', session)
    if session.REQUEST_METHOD == 'GET':
      resource_map = GetResourceMap(self._env)
      if resource_map is None:
        return session.BadRequest400()
      return session.Respond(resource_map)
    return session.BadRequest400()
