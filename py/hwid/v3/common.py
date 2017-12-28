# -*- coding: utf-8 -*-
#
# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common classes for HWID v3 operation."""

import json

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import type_utils


UNPROBEABLE_COMPONENT_ERROR = lambda comp_cls: (
    'Component class %r is unprobeable' % comp_cls)
MISSING_COMPONENT_ERROR = lambda comp_cls: 'Missing %r component' % comp_cls
AMBIGUOUS_COMPONENT_ERROR = lambda comp_cls, probed_value, comp_names: (
    'Ambiguous probe values %s of %r component. Possible components are: %r' %
    (json.dumps(probed_value, indent=2), comp_cls, sorted(comp_names)))
INVALID_COMPONENT_ERROR = lambda comp_cls, probed_value: (
    'Invalid %r component found with probe result %s '
    '(no matching name in the component DB)' % (
        comp_cls, json.dumps(probed_value, indent=2)))
UNSUPPORTED_COMPONENT_ERROR = lambda comp_cls, comp_name, comp_status: (
    'Component %r of %r is %s' % (comp_name, comp_cls, comp_status))


HEADER_BITS = 5
OPERATION_MODE = type_utils.Enum(['normal', 'rma', 'no_check'])
COMPONENT_STATUS = type_utils.Enum(['supported', 'deprecated',
                                    'unsupported', 'unqualified'])
ENCODING_SCHEME = type_utils.Enum(['base32', 'base8192'])


class HWIDException(Exception):
  """HWID-related exception."""
  pass
