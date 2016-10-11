#!/usr/bin/env python
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility module to load and validate a configuration file in JSON.

Usage:
 # test.json ----------------------------------------------------------------

 {"some_config": 1}

 # test.schema.json, created from jsonschema.net ----------------------------

 {"$schema":"http://json-schema.org/draft-04/schema#","type":"object",
  "properties":{"some_config":{"type":"integer"}},"required":["some_config"]}

 # test.py ------------------------------------------------------------------

 import factory_common
 from cros.factory.utils import config_utils

 # This example will load test.json and validate using test.schema.json.

 def test_config():
   # Load the config having same name as current module.
   config = config_utils.LoadConfig()
   print(config['some_config'])

   # To override additional settings, use OverrideConfig.
   config_utils.OverrideConfig(config, {'some_config': 2})

   # To use config in dot.notation, convert with GetNamedTuple
   config_nt = config_utils.GetNamedTuple(config)
   print(config_nt.some_config)

 test_config()

 # Execution result ---------------------------------------------------------

 # python ./test.py
 1
 2
"""

from __future__ import print_function

import collections
import inspect
import json
import logging
import os
import zipimport

# To simplify portability issues, validating JSON schema is optional.
try:
  import jsonschema
  _CAN_VALIDATE_SCHEMA = True
except Exception:
  _CAN_VALIDATE_SCHEMA = False


# Constants defined.
_CONFIG_FILE_EXT = '.json'
_SCHEMA_FILE_EXT = '.schema.json'
_CONFIG_BUILD_DIR = 'config'

# Config names in config_utils.json
_CONFIG_NAME_BUILD_DIR = 'BuildConfigDirectory'
_CONFIG_NAME_RUNTIME_DIR = 'RuntimeConfigDirectory'
_CONFIG_NAME_LOGGING = 'Logging'

# Cache of configuration for config_utils itself.
_CACHED_CONFIG_UTILS_CONFIG = None


def _DummyLogger(*unused_arg, **unused_kargs):
  """A dummy log function."""
  pass


def OverrideConfig(base, overrides):
  """Recursively overrides non-mapping values inside a mapping object.

  Args:
    base: A mapping object with existing data.
    overrides: A mapping to override values in base.

  Returns:
    The new mapping object with values overridden.
  """
  for k, v in overrides.iteritems():
    if isinstance(v, collections.Mapping):
      base[k] = OverrideConfig(base.get(k, {}), v)
    else:
      base[k] = overrides[k]
  return base


def GetNamedTuple(mapping):
  """Converts a mapping object into Named Tuple recursively.

  Args:
    mapping: A mapping object to be converted.

  Returns:
    A named tuple generated from argument.
  """
  if not isinstance(mapping, collections.Mapping):
    return mapping
  new_mapping = dict((k, GetNamedTuple(v)) for k, v in mapping.iteritems())
  return collections.namedtuple('Config', new_mapping.iterkeys())(**new_mapping)


def _LoadJsonFile(file_path, logger):
  """Loads a JSON file from specified path.

  Supports loading JSON file from real file system, or a virtual path inside
  python archive (PAR).

  Returns:
    A parsed JSON object for contents in file_path argument, or None if file
    can't be found.
  """
  if os.path.exists(file_path):
    logger('config_utils: Loading from %s', file_path)
    with open(file_path) as f:
      return json.load(f)

  # file_path does not exist, but it may be a PAR virtual path.
  if '.par' in file_path.lower():
    try:
      file_dir = os.path.dirname(file_path)
      file_name = os.path.basename(file_path)
      importer = zipimport.zipimporter(file_dir)
      zip_path = os.path.join(importer.prefix, file_name)
      logger('config_utils: Loading from %s!%s', importer.archive, zip_path)
      return json.loads(importer.get_data(zip_path))
    except zipimport.ZipImportError:
      logger('config_utils: No PAR/ZIP in %s. Ignore.', file_path)
      pass
    except IOError:
      logger('config_utils: PAR path %s does not exist. Ignore.', file_path)
      pass

  return None


def _LoadRawConfig(config_dir, config_name, schema_name=None,
                   logger=_DummyLogger):
  """Internal function to load JSON config and schema from specified path.

  Returns:
    A pair (config, schema) of configuration and schema objects.
  """
  if schema_name is None:
    schema_name = config_name
  config_path = os.path.join(config_dir, config_name + _CONFIG_FILE_EXT)
  schema_path = os.path.join(config_dir, schema_name + _SCHEMA_FILE_EXT)
  logger('config_utils: Checking %s', config_path)
  return _LoadJsonFile(config_path, logger), _LoadJsonFile(schema_path, logger)


def _LoadConfigUtilsConfig():
  """Internal function to load the config for config_utils itself."""
  global _CACHED_CONFIG_UTILS_CONFIG  # pylint: disable=global-statement

  if _CACHED_CONFIG_UTILS_CONFIG:
    return _CACHED_CONFIG_UTILS_CONFIG

  def _NormalizePath(config, key, base):
    if not os.path.isabs(config[key]):
      config[key] = os.path.normpath(os.path.join(base, config[key]))

  def _ApplyConfig(config, key):
    new_config, new_schema = _LoadRawConfig(
        config[key] if key else module_dir, module_name)
    OverrideConfig(config, new_config or {})
    _NormalizePath(config, _CONFIG_NAME_BUILD_DIR, module_dir)
    _NormalizePath(config, _CONFIG_NAME_RUNTIME_DIR, module_dir)
    return new_schema

  module_dir = os.path.realpath(os.path.dirname(__file__))
  module_name = os.path.splitext(os.path.basename(__file__))[0]

  config = {}
  schema = _ApplyConfig(config, None)
  build_schema = _ApplyConfig(config, _CONFIG_NAME_BUILD_DIR)
  runtime_schema = _ApplyConfig(config, _CONFIG_NAME_RUNTIME_DIR)

  schema = runtime_schema or build_schema or schema
  if _CAN_VALIDATE_SCHEMA:
    jsonschema.validate(config, schema)

  _CACHED_CONFIG_UTILS_CONFIG = config
  return config


def GetDefaultConfigInfo(module, module_file=None):
  """Gets the information of where is the default configuration data.

  Args:
    module: A module instance to find configuration name and path.
    module_file: fallback for module file name if module.__file__ cannot be
        retrieved.

  Returns:
    A pair of strings (name, directory) that name is the config name and
    directory is where the config should exist.
  """
  default_name = None
  default_dir = '.'

  path = (module.__file__ if module and getattr(module, '__file__') else
          module_file)

  if path:
    default_dir = os.path.dirname(path)
    default_name = os.path.splitext(os.path.basename(path))[0]
  return default_name, default_dir


def GetRuntimeConfigDirectory():
  """Returns a string for directory of runtime configuration data."""
  return _LoadConfigUtilsConfig()[_CONFIG_NAME_RUNTIME_DIR]


def GetBuildConfigDirectory():
  """Returns a string for directory of pre-build configuration data."""
  return _LoadConfigUtilsConfig()[_CONFIG_NAME_BUILD_DIR]


def _GetLogger():
  """Returns a function for logging debug messages.

  Returns logging.debug if the config_util's default config "Logging" is true,
  otherwise _DummyLogger.
  """
  return (logging.debug if _LoadConfigUtilsConfig()[_CONFIG_NAME_LOGGING] else
          _DummyLogger)


def LoadConfig(config_name=None, schema_name=None, validate_schema=True,
               default_config_dir=None):
  """Loads a configuration as mapping by given file name.

  The config files are retrieved and overridden in order:
   1. Default config directory: The arg 'default_config_dir' or the directory of
      caller module (or current folder if no caller module).
   2. Build config directory: The 'BuildConfigDirectory' in config_utils.json,
      should be set to 'root of project files'. Defaults to
      /usr/local/factory/py/config.
   3. Runtime config directory: The 'RuntimeConfigDirectory' in
      config_utils.json. Defaults to /var/factory/config.

  Args:
    config_name: a string for config file name (without extension) to read.
    schema_name: a string for schema file name (without extension) to read.
    validate_schema: boolean to indicate if schema should be checked.

  Returns:
    The config as mapping object.
  """
  config = {}
  schema = {}
  caller = inspect.stack()[1]
  # When running as pyc inside ZIP(PAR), getmodule() will fail.
  default_name, default_dir = GetDefaultConfigInfo(
      inspect.getmodule(caller[0]), caller[1])
  config_dirs = [
      default_config_dir or default_dir,
      GetBuildConfigDirectory(),
      GetRuntimeConfigDirectory(),
  ]
  logger = _GetLogger()
  if config_name is None:
    config_name = default_name
  assert config_name, 'LoadConfig() requires a config name.'

  found_config = False
  for config_dir in config_dirs:
    new_config, new_schema = _LoadRawConfig(
        config_dir, config_name, schema_name, logger)

    if new_config is not None:
      found_config = True
      OverrideConfig(config, new_config)

    if new_schema is not None:
      # Config data can be extended, but schema must be self-contained.
      schema = new_schema
  assert found_config, 'No configuration files found for %s.' % config_name

  # Ideally we should enforce validating schema, but currently many environments
  # where our factory software needs to live (i.e., old ChromeOS test images,
  # Windows, Ubuntu, or Android) may not have jsonschema library installed, so
  # we'd like to make _CAN_VALIDATE_SCHEMA optional and enforce it once we have
  # completed migration for config API.
  if validate_schema:
    assert schema, 'Need JSON schema file defined for %s.' % config_name
    if _CAN_VALIDATE_SCHEMA:
      jsonschema.validate(config, schema)
    else:
      logger('Configuration schema <%s> not validated because jsonschema '
             'Python library not installed.', config_name)
  else:
    logger('Skip validating schema for config <%s>.', config_name)
  return config
