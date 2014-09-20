# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""YAML utilities."""

import yaml


class BaseYAMLTagMetaclass(type):
  """Base metaclass for creating YAML tags."""
  YAML_TAG = None

  @classmethod
  def YAMLConstructor(mcs, loader, node):
    raise NotImplementedError

  @classmethod
  def YAMLRepresenter(mcs, dumper, data):
    raise NotImplementedError

  def __init__(mcs, name, bases, attrs):
    yaml.add_constructor(mcs.YAML_TAG, mcs.YAMLConstructor)
    yaml.add_representer(mcs, mcs.YAMLRepresenter)
    super(BaseYAMLTagMetaclass, mcs).__init__(name, bases, attrs)
