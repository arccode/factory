# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Wrapper for loading external module."""

import importlib
import os


def _ExternalWrapperLoadModule(file_name, context):
  name = os.path.splitext(os.path.basename(file_name))[0]
  module = None
  result = False
  try:
    module = importlib.import_module(name)
    result = True
  except Exception:
    # Only stop if required.
    if os.getenv('DEBUG_IMPORT'):
      raise

  if not module:
    # Try to load from dummy implementation. This should not change
    # MODULE_READY.
    name = 'cros.factory.external._dummy.' + name
    try:
      module = importlib.import_module(name)
    except Exception:
      pass

  if module:
    # Publish everything from module.
    context.update(module.__dict__)

  return result


MODULE_READY = _ExternalWrapperLoadModule(__file__, locals())
