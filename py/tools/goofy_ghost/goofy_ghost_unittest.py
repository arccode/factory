#!/usr/bin/env python2
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


import json
import os
import unittest

import jsonschema


class GoofyGhostSchemaTest(unittest.TestCase):

  def loadJSON(self, name):
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(parent_dir, name), 'r') as fin:
      return json.load(fin)

  def runTest(self):
    schema = self.loadJSON('goofy_ghost.schema.json')
    jsonschema.validate(self.loadJSON('goofy_ghost.json'), schema)
    jsonschema.validate(self.loadJSON('goofy_ghost.sample.json'), schema)


if __name__ == '__main__':
  unittest.main()
