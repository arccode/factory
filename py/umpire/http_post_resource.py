# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# pylint: disable=E1101

"""Umpire HTTP POST resource of site.

The class handles http://umpire_address:umpire_http_port/upload/
"""

import json
import logging

from twisted.web import http
from twisted.web import resource
from twisted.web import server

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import post_handler


_PATH_INFO = '/upload'


class HTTPPOSTResource(resource.Resource):
  """HTTP POST request handler.

  Args:
    env: An UmpireEnv object.
  """

  def __init__(self, env):
    resource.Resource.__init__(self)
    self.env = env
    self.putChild('upload', HTTPPOSTUploadResource(self.env))

  def render_POST(self, request):
    """Twisted HTTP POST request handler"""
    logging.info('request %s\n\n%s\n', request, dir(request))
    return server.NOT_DONE_YET


class HTTPPOSTUploadResource(resource.Resource):
  """HTTP POST upload request handler.

  Args:
    env: An UmpireEnv object.
  """
  def __init__(self, env):
    resource.Resource.__init__(self)
    self.env = env
    self.isLeaf = True

  def render_POST(self, request):
    if not request.postpath:
      logging.error('POST Upload: no handler name found')
      request.setResponseCode(http.BAD_REQUEST)
      request.finish()
      return resource.NoResource

    handler_name = request.postpath[-1]
    args = request.args

    # Try to find and call internal handler first, including call external
    # directly.
    d = None
    err = None
    func = post_handler.GetPostHandler(handler_name)
    if func:
      try:
        d = func(**args)
      except Exception as e:
        logging.error('POST Upload: internal handler raises %s', repr(e))
        err = e

    # If internal callable handler is not found, try external instead
    else:
      func = post_handler.GetPostHandler(post_handler.EXTERNAL)
      try:
        d = func(handler_name, **args)
      except Exception as e:
        # post_handler.external() should have handled exceptions.
        logging.error('POST Upload: external() raises %s', repr(e))
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

    if d:
      d.addCallback(_WriteResponse)
      d.addErrback(_WriteErrorResponse)
    else:
      _WriteErrorResponse(err)

    return server.NOT_DONE_YET
