# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging


# Add all default test renderer modules here. Modules not listed here will not
# be loaded by Minijack.
__all__ = ['default_renderer']


__renderers = dict()


def RegisterTestRenderer(test_type):
  """An decorator to register test renderer.

  Each test renderer should have one argument of type list(tuple(Event,
  dict(Attr.attr, Attr.value))), representing data of the test, and return
  a string that is the html content of rendered view.

  Args:
    test_type: If given 'default', set the function to be default render
               function for all tests. Else, set the function to be render
               function of test whose pytest_name or short path match
               test_type.
  """
  def wrapper(f):
    logging.info('Registered test renderer for %s', test_type)
    __renderers[test_type] = f
    return f
  return wrapper


def GetRegisteredRenderers():
  return __renderers
