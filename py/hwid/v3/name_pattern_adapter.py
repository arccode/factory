# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os.path
import re
import yaml


NAME_PATTERN_DIR = 'name_pattern/'


class NamePattern(object):
  def __init__(self, regex):
    self.patterns = [re.compile(s) for s in regex]

  def Matches(self, tag):
    return any(pat.match(tag) for pat in self.patterns)


class NamePatternAdapter(object):
  def __init__(self, filesystem_adapter):
    self.filesystem_adapter = filesystem_adapter
    self.name_patterns = {}
    for filename in self.filesystem_adapter.ListFiles(NAME_PATTERN_DIR):
      filepath = os.path.join(NAME_PATTERN_DIR, filename)
      category, unused_ext = os.path.splitext(filename)
      regexes = yaml.load(filesystem_adapter.ReadFile(filepath))
      self.name_patterns[category] = NamePattern(regexes)

  def GetNamePatterns(self, comp_cls):
    return self.name_patterns.get(comp_cls)
