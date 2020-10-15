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

import collections
import collections.abc
import glob
import inspect
import json
import logging
import os
import sys
import zipimport

from . import file_utils

# To simplify portability issues, validating JSON schema is optional.
try:
  # pylint: disable=wrong-import-order
  import jsonschema
  _CAN_VALIDATE_SCHEMA = True
except ImportError:
  _CAN_VALIDATE_SCHEMA = False


# Constants defined.
CONFIG_FILE_EXT = '.json'
SCHEMA_FILE_EXT = '.schema.json'

# Config names in config_utils.json
_CONFIG_NAME_BUILD_DIR = 'BuildConfigDirectory'
_CONFIG_NAME_RUNTIME_DIR = 'RuntimeConfigDirectory'
_CONFIG_NAME_LOGGING = 'Logging'

# Cache of configuration for config_utils itself.
_CACHED_CONFIG_UTILS_CONFIG = None

# Dummy cache for loop dependency detection.
_DUMMY_CACHE = object()

# Special key to delete a value when overriding config.
_OVERRIDE_DELETE_KEY = '__delete__'

# Special key to replace a dict value completely without merging with base when
# overriding config.
_OVERRIDE_REPLACE_KEY = '__replace__'

# Special key to list dependent configs.
_INHERIT_KEY = 'inherit'

# Special flag represents for the path of the directory where the caller module
# is located.
CALLER_DIR = None


class ConfigNotFoundError(Exception):
  pass


class _JsonFileInvalidError(Exception):
  def __init__(self, filename, detail):
    super(_JsonFileInvalidError, self).__init__(filename, detail)
    self.filename = filename
    self.detail = detail


class ConfigFileInvalidError(_JsonFileInvalidError):
  def __str__(self):
    return 'Failed to load the config file %r: %r' % (self.filename,
                                                      self.detail)


class SchemaFileInvalidError(_JsonFileInvalidError):
  def __str__(self):
    return 'Failed to load the schema file %r: %r' % (self.filename,
                                                      self.detail)


class ConfigInvalidError(Exception):
  def __init__(self, fail_reason, config_files):
    super(ConfigInvalidError, self).__init__(fail_reason, config_files)
    self.fail_reason = fail_reason
    self.config_files = config_files

  def __str__(self):
    return 'The config is invalid: %r\nThe config is loaded from:\n%s' % (
        self.fail_reason,
        '\n'.join('  ' + config_file for config_file in self.config_files))


def _DummyLogger(*unused_arg, **unused_kargs):
  """A dummy log function."""


def OverrideConfig(base, overrides, copy_on_write=False):
  """Recursively overrides non-mapping values inside a mapping object.

  Args:
    base: A mapping object with existing data.
    overrides: A mapping to override values in base.
    copy_on_write: if this is True, will make a copy of 'base' before
      overriding. 'base' itself will not be changed.

  Returns:
    The new mapping object with values overridden.
  """
  def pop_bool(dct, key):
    val = dct.pop(key, False)
    if not isinstance(val, bool):
      raise ValueError('Field %r should be a bool but %r found.' % (key, val))
    return val

  changed = False
  result = base.copy() if copy_on_write else base
  for k, v in overrides.items():
    if isinstance(v, collections.abc.Mapping):
      v = v.copy()
      if pop_bool(v, _OVERRIDE_DELETE_KEY):
        if k in result:
          result.pop(k)
          changed = True
      elif pop_bool(v, _OVERRIDE_REPLACE_KEY):
        result[k] = OverrideConfig({}, v)
        changed = True
      else:
        old_v = result.get(k)
        if isinstance(old_v, collections.abc.Mapping):
          result[k] = OverrideConfig(old_v, v, copy_on_write)
        else:
          result[k] = OverrideConfig({}, v)
        changed = True
    else:
      result[k] = v
      changed = True
  return result if changed else base


def GetNamedTuple(mapping):
  """Converts a mapping object into Named Tuple recursively.

  Args:
    mapping: A mapping object to be converted.

  Returns:
    A named tuple generated from argument.
  """
  if not isinstance(mapping, collections.abc.Mapping):
    return mapping
  new_mapping = {k: GetNamedTuple(v) for k, v in mapping.items()}
  return collections.namedtuple('Config', new_mapping.keys())(**new_mapping)


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
    try:
      with open(file_path) as f:
        return json.load(f)
    except Exception as e:
      raise _JsonFileInvalidError(file_path, str(e))

  # file_path does not exist, but it may be a PAR virtual path.
  if '.par' in file_path.lower():
    try:
      file_dir = os.path.dirname(file_path)
      file_name = os.path.basename(file_path)
      importer = zipimport.zipimporter(file_dir)
      zip_path = os.path.join(importer.prefix, file_name)
      logger('config_utils: Loading from %s!%s', importer.archive, zip_path)
      # importer.get_data will raise IOError if file wasn't found.
      return json.loads(importer.get_data(zip_path))
    except zipimport.ZipImportError:
      logger('config_utils: No PAR/ZIP in %s. Ignore.', file_path)
    except IOError:
      logger('config_utils: PAR path %s does not exist. Ignore.', file_path)
    except Exception as e:
      raise _JsonFileInvalidError(file_path, str(e))
  return None


def _LoadRawConfig(config_dir, config_name, logger=_DummyLogger):
  """Internal function to load JSON config from specified path.

  Returns:
    A configuration object.
  """
  try:
    config_path = os.path.join(config_dir, config_name + CONFIG_FILE_EXT)
    logger('config_utils: Checking %s', config_path)
    return _LoadJsonFile(config_path, logger)
  except _JsonFileInvalidError as e:
    raise ConfigFileInvalidError(e.filename, e.detail)


def _LoadRawSchema(config_dir, schema_name, logger=_DummyLogger):
  """Internal function to load JSON schema from specified path.

  Returns:
    A schema object.
  """
  try:
    schema_path = os.path.join(config_dir, schema_name + SCHEMA_FILE_EXT)
    return _LoadJsonFile(schema_path, logger)
  except _JsonFileInvalidError as e:
    raise SchemaFileInvalidError(e.filename, e.detail)


def _LoadConfigUtilsConfig():
  """Internal function to load the config for config_utils itself."""
  global _CACHED_CONFIG_UTILS_CONFIG  # pylint: disable=global-statement

  if _CACHED_CONFIG_UTILS_CONFIG:
    return _CACHED_CONFIG_UTILS_CONFIG

  def _NormalizePath(key):
    if not os.path.isabs(config[key]):
      config[key] = os.path.normpath(os.path.join(module_dir, config[key]))

  def _ApplyConfig(key):
    config_dir = config[key] if key else module_dir
    new_config = _LoadRawConfig(config_dir, module_name)
    OverrideConfig(config, new_config or {})
    _NormalizePath(_CONFIG_NAME_BUILD_DIR)
    _NormalizePath(_CONFIG_NAME_RUNTIME_DIR)
    return _LoadRawSchema(config_dir, module_name)

  module_dir = os.path.realpath(os.path.dirname(__file__))
  module_name = os.path.splitext(os.path.basename(__file__))[0]

  config = {}
  schema = _ApplyConfig(None)
  build_schema = _ApplyConfig(_CONFIG_NAME_BUILD_DIR)
  runtime_schema = _ApplyConfig(_CONFIG_NAME_RUNTIME_DIR)

  if _CAN_VALIDATE_SCHEMA:
    jsonschema.validate(config, runtime_schema or build_schema or schema)

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
  path = os.path.realpath(getattr(module, '__file__', module_file))
  return (os.path.splitext(os.path.basename(path))[0], os.path.dirname(path))


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


def DeleteRuntimeConfig(config_name):
  """Removes the configuration in Runtime config directory.

  This is helpful for tests to reset or delete corrupted configurations.

  Args:
    config_name: a string for config file name (without extension) to delete.
  """
  file_utils.TryUnlink(
      os.path.join(GetRuntimeConfigDirectory(), config_name + CONFIG_FILE_EXT))


def SaveRuntimeConfig(config_name, value):
  """Saves a configuration to Runtime config directory.

  Args:
    config_name: a string for config file name (without extension) to write.
    value: the config data to write (will be serialized by ``json.dumps``).
  """
  runtime_dir = GetRuntimeConfigDirectory()
  if not os.path.exists(runtime_dir):
    os.makedirs(runtime_dir)
  save_path = os.path.join(
      GetRuntimeConfigDirectory(), config_name + CONFIG_FILE_EXT)

  # Try to save in atomic way. This is similar to file_utils.AtomicWrite but we
  # want to have a dedicated implementation here to reduce dependency.
  tmp_path = save_path + '~'
  old_path = save_path + '.old'
  with open(tmp_path, 'w') as output:
    output.write(json.dumps(value))
    output.flush()
    os.fdatasync(output.fileno())
  if os.path.exists(old_path):
    # Remove old files first so we can use os.rename instead of shutil.move.
    os.remove(old_path)
  if os.path.exists(save_path):
    os.rename(save_path, old_path)
  os.rename(tmp_path, save_path)
  # Python 2.7 does not have os.sync so let's sync the folder. This is same
  # as file_utils.SyncDirectory but we want a dedicated implementation here to
  # reduce module dependency.
  try:
    dir_fd = os.open(os.path.dirname(save_path), os.O_DIRECTORY)
    os.fsync(dir_fd)
  finally:
    try:
      os.close(dir_fd)
    except Exception:
      pass


def _ResolveConfigInfo(config_name, frame, extra_config_dirs):
  config_dirs = [
      GetRuntimeConfigDirectory(),
      GetBuildConfigDirectory(),
  ]

  module_file = inspect.getframeinfo(frame)[0]
  # When running as pyc inside ZIP(PAR), getmodule() will fail.
  default_config_name, caller_dir = GetDefaultConfigInfo(
      inspect.getmodule(frame), module_file)

  caller_dirs = [caller_dir]
  # If the file is a symbolic link, we also search it's original path.
  if os.path.islink(module_file):
    caller_dirs.append(os.path.dirname(os.path.realpath(module_file)))

  for config_dir in reversed(extra_config_dirs):
    config_dirs += caller_dirs if config_dir == CALLER_DIR else [config_dir]

  return (config_name or default_config_name, config_dirs)


def LoadConfig(config_name=None, schema_name=None, validate_schema=True,
               default_config_dirs=CALLER_DIR, allow_inherit=False,
               generate_depend=False):
  """Loads a configuration as mapping by given file name.

  The config files are retrieved and overridden in order:
   1. Default config directory(s): See "Args" section for detail.
   2. Build config directory: The 'BuildConfigDirectory' in config_utils.json,
      should be set to 'root of project files'. Defaults to
      /usr/local/factory/py/config.
   3. Runtime config directory: The 'RuntimeConfigDirectory' in
      config_utils.json. Defaults to /var/factory/config.

  Args:
    config_name: a string for config file name (without extension) to read.
    schema_name: a string for schema file name (without extension) to read.
    validate_schema: boolean to indicate if schema should be checked.
    default_config_dirs: A list of directories in which the config files are
        retrieved.  If the caller only want to specify one directory, it can
        also specify the directory directly instead of wrap it into a list with
        single element.  Each element of the list could be either a string or
        `config_util.CALLER_DIR`.  A string represents the path of the
        directory.  The special flag `config_util.CALLER_DIR` means the
        directory of caller module (or current folder if no caller module).  If
        the caller module is a symbolic link, we search its original path first,
        and override it with the config beside the symbolic link if exists.
    allow_inherit: if set to True, try to read 'inherit' from the
        loaded config. It should be the name of the parent config to be loaded,
        and will then be overridden by the current config. It can also be a list
        of parent config names, and will be overridden in reversed order.

        For example, if we're loading config "A" with:
        1. {"inherit": "B"}
           "B" will be loaded and overridden by "A".
        2. {"inherit": ["B", "C", "D"]},
           "D" will be loaded first, overridden by "C", and by "B",
           and then by "A".

        Note that this is done after all the directory-based overriding is
        finished.

        Schema check is performed after overriding if validate_schema is True.

    generate_depend: if this is True, will collect all dependencies of the
        config file, calling `GetDepend` function will return a list of files
        loaded to generate this config.  For example, if we're loading config
        "A" with: {"inherit": "B"}, then

           A.GetDepend() = [<path to A>, <path to B>, <what B depends on ...>]

        The order of paths is same as the result of C3 linearization of the
        inherited config names.

        Note that we are returning "path of config files it depends on", so
        paths under build config directory and runtime config directory are
        returned too.

        If `generate_depend` is False, `A.GetDepend()` will be empty.

  Returns:
    The config as mapping object.

  Raises:
    - `ConfigNotFoundError` if no available config is found.
    - `ConfigFileInvalidError` if the config files are found, but it fails
        to load one of them.
    - `SchemaFileInvalidError` if the schema file is invalid.
    - `ConfigInvalidError` if the resolved config is invalid.
  """
  if not isinstance(default_config_dirs, list):
    default_config_dirs = [default_config_dirs]

  current_frame = sys._getframe(1)  # pylint: disable=protected-access
  config_name, config_dirs = _ResolveConfigInfo(
      config_name, current_frame, default_config_dirs)

  if not config_name:
    raise ConfigNotFoundError('LoadConfig() requires a config name.')

  logger = _GetLogger()
  raw_config_list = _LoadRawConfigList(config_name, config_dirs, allow_inherit,
                                       logger, {})
  config = raw_config_list.Resolve()

  # Remove the special key so that we don't need to write schema for this field.
  if allow_inherit:
    config.pop(_INHERIT_KEY, None)

  # Ideally we should enforce validating schema, but currently many environments
  # where our factory software needs to live (i.e., old ChromeOS test images,
  # Windows, Ubuntu, or Android) may not have jsonschema library installed, so
  # we'd like to make _CAN_VALIDATE_SCHEMA optional and enforce it once we have
  # completed migration for config API.
  if validate_schema:
    schema = {}
    for config_dir in config_dirs:
      new_schema = _LoadRawSchema(
          config_dir, schema_name or config_name, logger)

      if new_schema is not None:
        # Config data can be extended, but schema must be self-contained.
        schema = new_schema
        break
    assert schema, 'Need JSON schema file defined for %s.' % config_name
    if _CAN_VALIDATE_SCHEMA:
      try:
        jsonschema.validate(config, schema)
      except Exception as e:
        # Only get the `message` property of the exception to prevent
        # from dumping whole schema data in the log.
        raise ConfigInvalidError(str(e), raw_config_list.CollectDepend())

    else:
      logger('Configuration schema <%s> not validated because jsonschema '
             'Python library not installed.', config_name)
  else:
    logger('Skip validating schema for config <%s>.', config_name)

  config = ResolvedConfig(config)
  if generate_depend:
    config.SetDepend(raw_config_list.CollectDepend())
  return config


def GlobConfig(config_pattern, default_config_dirs=CALLER_DIR):
  """Globs a configuration by given configuration name pattern.

  The config files are located in multiple directories (see `LoadConfig` for
  detail) and it's hard to find all of them.  This function helps the caller
  to search the matched configuration names in multiple directories.

  Args:
    config_pattern: a string of config name pattern to match.
    default_config_dirs: A list of directories in which the config files are
        retrieved.  See `LoadConfig` for detail.

  Returns:
    A set of matched config names.
  """
  def _ToConfigName(path):
    return os.path.basename(path)[:-len(CONFIG_FILE_EXT)]

  if not isinstance(default_config_dirs, list):
    default_config_dirs = [default_config_dirs]

  current_frame = sys._getframe(1)  # pylint: disable=protected-access
  unused_config_name, config_dirs = _ResolveConfigInfo(
      None, current_frame, default_config_dirs)

  ret = set()
  for config_dir in config_dirs:
    pattern = os.path.join(config_dir, config_pattern + CONFIG_FILE_EXT)
    ret |= set(_ToConfigName(p) for p in glob.iglob(pattern))
  return ret


class _ConfigList(collections.OrderedDict):
  """Internal structure to store a list of raw configs."""
  def Resolve(self):
    """Returns the final config after overriding."""
    ret = {}
    # collections.OrderedDict does support reversed().
    for key in reversed(self):  # pylint: disable=bad-reversed-sequence
      for unused_config_dir, config in reversed(self[key]):
        ret = OverrideConfig(ret, config)
    return ret

  def CollectDepend(self):
    """Returns a list of all files loaded for this config list.

    Returns:
      a list of paths (strings).
    """
    depends = []
    for config_name in self:
      for config_dir, unused_config in self[config_name]:
        depends.append(os.path.join(config_dir, config_name + CONFIG_FILE_EXT))
    return depends


class ResolvedConfig(dict):
  """A resolved config with extra information.

  This class inherits dict so all dict operations should work on its instances.
  """
  def __init__(self, *args, **kwargs):
    super(ResolvedConfig, self).__init__(*args, **kwargs)
    self._recipe = []

  def SetDepend(self, paths):
    """Set list of files loaded to resolve this config."""
    self._recipe = paths

  def GetDepend(self):
    return self._recipe


def _C3Linearization(parent_configs, config_name):
  """C3 superclass linearization for inherited configs.

  This is the same as the algorithm used for Python new style class multiple
  inheritance.
  """
  def FirstKey(odict):
    return next(iter(odict))
  # We collect all configs into all_configs, and only use keys in parent_configs
  # as OrderedSet afterward.
  all_configs = {}
  parents = collections.OrderedDict()
  for config_list in parent_configs:
    all_configs.update(config_list)
    # Only key is used, value is not important.
    parents[FirstKey(config_list)] = None

  parent_lists = [l.copy() for l in parent_configs]
  parent_lists.append(parents)

  def GoodHead(x):
    return all(x not in l or x == FirstKey(l) for l in parent_lists)

  ret = _ConfigList()
  while any(parent_lists):
    head = next((head for head in (FirstKey(l) for l in parent_lists if l)
                 if GoodHead(head)), None)
    if head is None:
      logging.info('original items:\n%s',
                   "\n".join(repr(list(l)) for l in parent_configs))
      logging.info('current items:\n%s',
                   "\n".join(repr(list(l)) for l in parent_lists))
      raise RuntimeError('C3 linearization failed for %s' % config_name)
    ret[head] = all_configs[head]
    for l in parent_lists:
      if l and FirstKey(l) == head:
        l.popitem(last=False)
  return ret


def _LoadRawConfigList(config_name, config_dirs, allow_inherit,
                       logger, cached_configs):
  """Internal function to load the config list."""
  if config_name in cached_configs:
    assert cached_configs[config_name] != _DUMMY_CACHE, (
        'Detected loop inheritance dependency of %s' % config_name)
    return cached_configs[config_name]

  # Mark the current config in loading.
  cached_configs[config_name] = _DUMMY_CACHE

  config_list = _ConfigList()

  found_configs = []
  for config_dir in config_dirs:
    new_config = _LoadRawConfig(config_dir, config_name, logger)

    if new_config is not None:
      found_configs.append((config_dir, new_config))
  if not found_configs:
    raise ConfigNotFoundError(
        'No configuration files found for %s.' % config_name)
  config_list[config_name] = found_configs

  # Get the current config dict.
  config = config_list.Resolve()

  if allow_inherit and isinstance(config, dict) and _INHERIT_KEY in config:
    parents = config[_INHERIT_KEY]
    if isinstance(parents, str):
      parents = [parents]

    # Ignore if 'inherit' is not a list of parent names.
    if not isinstance(parents, list):
      logging.warning('Key "inherit" is reserved for listing dependent '
                      'configurations.')
    else:
      parent_configs = []
      for parent in parents:
        current_config = _LoadRawConfigList(
            config_name=parent,
            config_dirs=config_dirs,
            allow_inherit=allow_inherit,
            cached_configs=cached_configs,
            logger=logger)
        parent_configs.append(current_config)
      config_list.update(_C3Linearization(parent_configs, config_name))

  cached_configs[config_name] = config_list
  return config_list
