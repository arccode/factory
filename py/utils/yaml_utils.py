# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""YAML utilities."""

import collections
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

  def __init__(cls, name, bases, attrs, loader=yaml.Loader, dumper=yaml.Dumper):
    yaml.add_constructor(cls.YAML_TAG, cls.YAMLConstructor, Loader=loader)
    yaml.add_representer(cls, cls.YAMLRepresenter, Dumper=dumper)
    super(BaseYAMLTagMetaclass, cls).__init__(name, bases, attrs)


def ParseMappingAsOrderedDict(enable=True,
                              loader=yaml.Loader,
                              dumper=yaml.Dumper):
  """Treat OrderedDict as the default mapping instance.

  While we load a yaml file to a object, modify the object, and dump to a yaml
  file, we hope to keep the order of the mapping instance. Therefore, we should
  parse the mapping to the Python OrderedDict object, and dump the OrderedDict
  instance to yaml just like a dict object.

  Args:
    enable: if enable is True, load and dump yaml as OrderedDict.
  """
  def DictRepresenter(dumper, data):
    return dumper.represent_dict(data.iteritems())

  def OrderedDictRepresenter(dumper, data):
    return dumper.represent_object(data)

  def OrderedDictConstructor(loader, node):
    return collections.OrderedDict(loader.construct_pairs(node))

  def DictConstructor(loader, node):
    return dict(loader.construct_pairs(node))

  if enable:
    # Represent OrderedDict object like a dict.
    # Construct the yaml mapping string to OrderedDict.
    yaml.add_representer(collections.OrderedDict, DictRepresenter,
                         Dumper=dumper)
    yaml.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                         OrderedDictConstructor, Loader=loader)
  else:
    # Set back to normal.
    yaml.add_representer(collections.OrderedDict, OrderedDictRepresenter,
                         Dumper=dumper)
    yaml.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                         DictConstructor, Loader=loader)
