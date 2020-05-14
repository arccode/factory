# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A collective of webapp-related functions."""

import http.cookies

from cros.factory.umpire import common


def ParseDUTHeader(header):
  """Parses X-Umpire-DUT embedded in DUT's request.

  It checks if it only contains key(s) defined in DUT_INFO_KEYS or
  LEGACY_DUT_INFO_KEYS.  All legacy key-value pairs will be ignored and will
  not be contained in the return result.

  Args:
    header: DUT info embedded in header X-Umpire-DUT. It is a string of
        "key=value; key=value ...", which is the same as HTTP Cookie.

  Returns:
    A dict of DUT info.

  Raises:
    ValueError if header is ill-formed.
  """
  def ValidKey(key):
    if key in common.DUT_INFO_KEYS:
      return True
    if key in common.LEGACY_DUT_INFO_KEYS:
      return True
    if any(key.startswith(prefix) for prefix in common.DUT_INFO_KEY_PREFIX):
      return True
    return False

  dut_info = http.cookies.SimpleCookie()
  dut_info.load(header)
  invalid_keys = [key for key in dut_info if not ValidKey(key)]
  if invalid_keys:
    raise ValueError('Invalid key(s): %r' % invalid_keys)

  return {k: v.value for k, v in dut_info.items()
          if k not in common.LEGACY_DUT_INFO_KEYS}
