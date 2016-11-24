# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# pylint: disable=E1101

"""Umpire HTTP POST resource of site.

The class handles http://umpire_address:umpire_http_port/post/
"""

import json
import logging
from twisted.web import http
from twisted.web import resource
from twisted.web import server

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import post_handler


class HTTPPOSTResource(resource.Resource):
  """HTTP POST request handler.

  Args:
    env: An UmpireEnv object.
  """

  def __init__(self, env):
    resource.Resource.__init__(self)
    self.env = env
    # Paths here must match service/http.py
    self.putChild('post', HTTPPOSTGenericResource(self.env))
    # Backward compatible.
    self.putChild('upload', HTTPPOSTGenericResource(self.env))

  def render_POST(self, request):
    """Twisted HTTP POST request handler"""
    logging.info('request %s\n\n%s\n', request, dir(request))
    return server.NOT_DONE_YET


class HTTPPOSTGenericResource(resource.Resource):
  """HTTP POST generic request handler.

  Args:
    env: An UmpireEnv object.
  """

  def __init__(self, env):
    resource.Resource.__init__(self)
    self.env = env
    self.isLeaf = True

  def render_POST(self, request):
    if not request.postpath:
      logging.error('POST: no handler name found')
      request.setResponseCode(http.BAD_REQUEST)
      return ''

    handler_name = request.postpath[-1]
    args = request.args

    # Try to find and call internal handler first, including call external
    # directly.
    result = None
    err = None
    func = post_handler.GetPostHandler(handler_name)
    if func:
      try:
        result = func(self.env, **args)
      except Exception as e:
        logging.error('POST: internal handler raises %r', e)
        err = e

    # If internal callable handler is not found, try external instead
    else:
      try:
        result = post_handler.RunExternalHandler(self.env, handler_name, **args)
      except Exception as e:
        # post_handler.external() should have handled exceptions.
        logging.error('POST: external(%s) raises %r', handler_name, e)
        err = e

    def _WriteResponse(result):
      status, content = result
      # Write result in text/plain json-encoded string
      request.setResponseCode(status)
      request.defaultContentType = 'text/plain; charset=utf-8'
      request.write(json.dumps(content))
      request.finish()

    def _WriteErrorResponse(e):
      _WriteResponse((http.INTERNAL_SERVER_ERROR, {'exception': repr(e)}))

    if result:
      result.addCallback(_WriteResponse)
      result.addErrback(_WriteErrorResponse)
    else:
      _WriteErrorResponse(err)

    return server.NOT_DONE_YET
