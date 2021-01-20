# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re


_SUPPORTED_CATEGORIES = set([
    'wireless',
])


def GetSupportedCategories():
  return _SUPPORTED_CATEGORIES


class NamePattern:
  def __init__(self, regex):
    self.pattern = re.compile(regex)

  def Matches(self, tag):
    ret = self.pattern.match(tag)
    if ret:
      return int(ret.group(1)), int(ret.group(2) or 0)
    return None


class NamePatternAdapter:

  def GetNamePattern(self, comp_cls):
    if comp_cls not in GetSupportedCategories():
      return None
    return NamePattern(r'{comp_cls}_(\d+)(?:_(\d+))?(?:#.*)?$'.format(
        comp_cls=re.escape(comp_cls)))
