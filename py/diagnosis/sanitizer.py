# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Sanitizes the YAML configs."""

import collections
import copy
import re

import factory_common  # pylint: disable=W0611

from cros.factory.diagnosis.common import FormatError
from cros.factory.diagnosis.common import INPUT_TYPE
from cros.factory.diagnosis.common import OPTIONS
from cros.factory.diagnosis.common import TOKEN
from cros.factory.utils.process_utils import SpawnOutput

_DEFAULT_INPUT_BOOL_VALUE = True
_DEFAULT_INPUT_FILE_PATTERN = '.*'
_DEFAULT_INPUT_FILE_TYPE = 'regular-file'

_DEFAULT_CONFIRM_TITLE = 'Confirm'
_DEFAULT_CONFIRM_OPTIONS = (OPTIONS.YES, OPTIONS.CANCEL)
_DEFAULT_CONFIRM_TIMEOUT = (10, OPTIONS.YES)
_DEFAULT_CONFIRM_EXPECTED_OUTPUT = 'yes'

_DEFAULT_TERMINATING_TIMEOUT = 5


def SanitizeConfig(configs):
  """Validates the YAML config and sets default value for missing fields.

  The config must be a list of tasks without repeated name.

  Args:
    configs: The YAML config.

  Returns:
    A sanitized configurations.
  """
  dup_configs = copy.deepcopy(configs)
  if not isinstance(dup_configs, list):
    raise FormatError('Value of the configurations is not a list')
  return [_SanitizeTask(x) for x in dup_configs]


def _SanitizeTask(config):
  """Validates task element and sets default value for missing fields.

  A task should have keys defined below:
    name: The name of the task.
    description: The description string of the task.
    inputs(optional when 'steps' is not in the config): A list contains input
        elements.
    steps(optional): A list contains each step to run.  If this key is not in
        the task, the task will become "not runnable".  This case is useful to
        create a group.
    member(optional): A list contains tasks.  The existance of this key let this
        task become a group of other tasks (PS1).

  Args:
    config: Task element.

  Returns:
    A sanitized task element.
  """
  _SanitizeDefaultValueAndType(config, [(TOKEN.NAME, '', basestring),
                                        (TOKEN.DESCRIPTION, '', basestring)])
  try:
    if TOKEN.STEPS in config:
      if not isinstance(config[TOKEN.STEPS], list):
        raise FormatError('Value of %r is not a %r' % (TOKEN.STEPS, 'list'))
      config[TOKEN.STEPS] = [_SanitizeStep(x) for x in config[TOKEN.STEPS]]
      _SanitizeDefaultValueAndType(config, [(TOKEN.INPUTS, [], list)])
      config[TOKEN.INPUTS] = _SanitizeInputs(config[TOKEN.INPUTS])
    if TOKEN.MEMBER in config:
      if not isinstance(config[TOKEN.MEMBER], list):
        raise FormatError('Value of %r is not a %r' % (TOKEN.MEMBER, 'list'))
      config[TOKEN.MEMBER] = [_SanitizeTask(x) for x in config[TOKEN.MEMBER]]
      count = collections.Counter(x[TOKEN.NAME] for x in config[TOKEN.MEMBER])
      repeat_names = [x for x in count if count[x] > 1]
      for repeat_name in repeat_names:
        raise FormatError('Same sub-task name: %r' % repeat_name)
    return config
  except FormatError as e:
    raise FormatError(config[TOKEN.NAME] + ":" + str(e))


def _SanitizeInputs(configs):
  """Validates inputs and sets default value for missing fields.

  It will sanitize each input element in it and then fill up the missing var_id.
  """
  configs = [_SanitizeInput(x) for x in configs]
  num_ids = [x[TOKEN.VAR_ID] for x in configs if x[TOKEN.VAR_ID] is not None]
  id_max = max(num_ids) if num_ids else 0
  for config in configs:
    if config[TOKEN.VAR_ID] is None:
      id_max += 1
      config[TOKEN.VAR_ID] = id_max
  return configs


def _SanitizeInput(config):
  """Validates input element and sets default value for missing fields.

  An input should belongs to a type (config['type']).  Each type has its
  required fields defined below:
    * number / slider:
      min: The minimum acceptable values (PS1).
      max: The maximum (inclusive) acceptable values.
      step: Interval between values.
      value: Default value.
      round: Number of decimal places.
    * choices:
      choices: A non-empty list stores all acceptable choices.
      value: Default value.
    * bool:
      value: Default value (True or False).
      enable_list: Input elements which will be enabled when true.
      disable_list: Input elements which will be disabled when true.
    * file:
      pattern: Acceptable file name's pattern in regular expression (PS2).
      file_type: File type.
    * string:
      value: Default value.
      hint: Hint string to show when the input field is empty.
      regexp: Acceptable string in regular expression.
    * button:
      add: A list contains what inputs should be added after user clicks this
          button.
      del: A list contains what input's var_ids should be removed after user
          clicks this button (PS3).

  In addition, no matter what type it is, an input element should contain fields
  defined below:
    * prompt: Prompt string to show at the left side of the input field in GUI.
    * help: Help string to show when then cursor moves above the input field in
        GUI.
    * var_id: A number to identify this input element.

  PS1: This value can be either a number or a string starts with "!", which
      means the program needs to run some linux command to get the value.  Also
      applies to max, step, value, and choices (PS4).
  PS2: It is a list contains two string, the first one is the regular expression
      and the second one is a string contains flags (see the doc about
      CreateRegExp for detail).
  PS3: After user clicks the button, it will remove inputs first.
  PS4: If "choices" is a string starts with "!", instead of a list contains
      strings, the DiagnosisTool will run the command and split the stdout text
      by space, tab or newline into a list.

  Args:
    config: Input element.

  Returns:
    A sanitized input element.
  """
  try:
    _SanitizeDefaultValueAndType(config, [
        (TOKEN.PROMPT, '', basestring),
        (TOKEN.HELP, '', basestring),
        (TOKEN.VAR_ID, None, (type(None), int))])
    config_type = config[TOKEN.TYPE].lower()
    if config_type == INPUT_TYPE.NUMBER or config_type == INPUT_TYPE.SLIDER:
      _SanitizeInputNumberAndSlider(config)

    elif config_type == INPUT_TYPE.CHOICES:
      _SanitizeInputChoices(config)

    elif config_type == INPUT_TYPE.BOOL:
      _SanitizeInputBool(config)

    elif config_type == INPUT_TYPE.FILE:
      _SanitizeInputFile(config)

    elif config_type == INPUT_TYPE.STRING:
      _SanitizeInputString(config)

    else:
      raise FormatError('Unknown input type: %r.' % config_type)

  except KeyError as e:
    raise FormatError('Key "%s" not found in the input element.' % str(e))
  except Exception as e:  # pylint: disable=W0703
    raise FormatError('Exception: "' + str(e) + '"')
  return config


def _SanitizeInputNumberAndSlider(ref):
  for key in [TOKEN.MIN, TOKEN.MAX, TOKEN.STEP]:
    if isinstance(ref[key], (int, float)):
      pass
    elif isinstance(ref[key], basestring) and ref[key].startswith('!'):
      ref[key] = _GetCommandOutput(ref[key][1:], float, 'float')
    else:
      raise FormatError('Value of %r is neither a number nor a command: %r' %
                        (key, ref[key]))
  _SanitizeDefaultValueAndType(ref, [
      (TOKEN.VALUE, ref[TOKEN.MIN], (int, float)),
      (TOKEN.ROUND, 0, (int, float)),
      (TOKEN.UNIT, '', basestring)])


def _SanitizeInputChoices(ref):
  key = TOKEN.CHOICES
  if isinstance(ref[key], list):
    pass
  elif isinstance(ref[key], basestring) and ref[key].startswith('!'):
    ref[key] = _GetCommandOutput(ref[key][1:], lambda x: re.split(' |\t|\n', x))
  else:
    raise FormatError('Value of %r is neither a number nor a command: %r' %
                      (key, ref[key]))
  ref[key] = [str(x) for x in ref[key] if str(x)]
  if not ref[key]:
    raise FormatError('No valid flag in %r.' % key)
  ref.setdefault(TOKEN.VALUE, ref[key][0])
  if ref[TOKEN.VALUE] not in ref[key]:
    raise FormatError('Default value is not a valid flag: %r.' %
                      ref[TOKEN.VALUE])


def _SanitizeInputBool(ref):
  _SanitizeDefaultValueAndType(ref, [
      (TOKEN.VALUE, _DEFAULT_INPUT_BOOL_VALUE, bool),
      (TOKEN.ENABLE_LIST, [], list),
      (TOKEN.DISABLE_LIST, [], list)])


def _SanitizeInputFile(ref):
  _SanitizeDefaultValueAndType(ref, [
      (TOKEN.PATTERN, _DEFAULT_INPUT_FILE_PATTERN, basestring),
      (TOKEN.FILE_TYPE, _DEFAULT_INPUT_FILE_TYPE, basestring)])


def _SanitizeInputString(ref):
  _SanitizeDefaultValueAndType(ref, [
      (TOKEN.VALUE, '', basestring),
      (TOKEN.REGEXP, None, (type(None), list)),
      (TOKEN.HINT, '', basestring)])
  if isinstance(ref[TOKEN.REGEXP], list):
    _SanitizeRegExp(ref[TOKEN.REGEXP], TOKEN.REGEXP)


def _SanitizeStep(config):
  """Validates step element and sets default value for missing fields.

  A step should belongs to a type.  Each type has its required fields defined
  below:
    * type "command" or "finally":
      command/finally (PS1): A linux command (string without prefix "!") to run.
      terminate_timeout: Timeout to stop this command.
      terminating_timeout: Timeout to kill this command after trying to stop it.
      expected_output: What output text you expect if the program finished
          successfully (PS2).
      error_message: Error message to show if the command failed.
    * type "confirm":
      confirm: A string to show to the user to confirm something.
      options: A list of string contain options to select.
      timeout: None or a list like [timeout, default_value].  When timeout, the
          confirm dialog will automatically select default_value.
      expected_output: What option you expect the user to select for successful.

  PS1: It is "command" if the type is "command".  Otherwise it is "finally".
  PS2: expected_output allow three forms:
      case 1, None:
        Whether the step is successful merely depends on command return code.
      case 2, A string:
        Whether the command successful or not depends on the stdout text is the
        same as this string.
      case 2, A list like [string1, string2]:
        Like case 2, but use regular expression (string1 is the expression,
        string2 is the re flags).

  Args:
    config: Step element.

  Returns:
    A sanitized step element.
  """
  found = 0
  if TOKEN.CONFIRM in config:
    if not isinstance(config[TOKEN.CONFIRM], basestring):
      raise FormatError("A confirm content must be a string")
    _SanitizeDefaultValueAndType(config, [
        (TOKEN.TITLE, _DEFAULT_CONFIRM_TITLE, basestring),
        (TOKEN.OPTIONS, list(_DEFAULT_CONFIRM_OPTIONS), list),
        (TOKEN.TIMEOUT, list(_DEFAULT_CONFIRM_TIMEOUT), (list, type(None)))])
    if not config[TOKEN.OPTIONS]:
      raise FormatError('No options for user to select.')
    config.setdefault(TOKEN.EXPECTED_OUTPUT, config[TOKEN.OPTIONS][0])
    if config[TOKEN.EXPECTED_OUTPUT] not in config[TOKEN.OPTIONS]:
      raise FormatError("expected_output not in the options: %r" %
                        config[TOKEN.EXPECTED_OUTPUT])
    found += 1
  for key in [x for x in [TOKEN.COMMAND, TOKEN.FINALLY] if x in config]:
    if not isinstance(config[key], basestring):
      raise FormatError("A linux shell command must be a string")
    _SanitizeDefaultValueAndType(config, [
        (TOKEN.TERMINATE_TIMEOUT, None, (int, type(None))),
        (TOKEN.TERMINATING_TIMEOUT, None, (int, type(None))),
        (TOKEN.EXPECTED_OUTPUT, None, (type(None), basestring, list)),
        (TOKEN.ERROR_MESSAGE, None, (type(None), basestring))])
    if isinstance(config[TOKEN.EXPECTED_OUTPUT], list):
      _SanitizeRegExp(config[TOKEN.EXPECTED_OUTPUT], TOKEN.EXPECTED_OUTPUT)
    found += 1
  if found != 1:
    raise FormatError('Unknown step type %r.' % config)
  return config


def _GetCommandOutput(command, converter, converted_type_name=None):
  """Gets the output of a command.

  Args:
    command: Command line.
    converter: A function to convert the output text of the command into right
        data type.
    converted_type_name: Name of the converted data type (This argument is used
        for raise more information when error occured).

  Returns:
    Output data converted by converter
  """
  try:
    output = SpawnOutput(command, shell=True)
  except Exception as e:  # pylint: disable=W0703
    raise FormatError('Runs command %r failed, reason %r' % (command, e))
  try:
    return converter(output)
  except Exception as e:  # pylint: disable=W0703
    raise FormatError('Cannot convert the output of %r to %s: %s' %
                      (command, converted_type_name, output))


def _SanitizeDefaultValueAndType(ref, value_type_list):
  """Sanitizes the values of specified keys in given input element.

  Args:
    ref: Reference from the input element.  Sanitization process will be applied
        on it without the duplicated one.
    value_type_list: A list contains lots of tuples, each contains key, default
        value and value type.
  """
  for (key, default_value, value_type) in value_type_list:
    ref.setdefault(key, default_value)
    if not isinstance(ref[key], value_type):
      raise FormatError('Value of %r is not a %r' % (key, value_type))


def _SanitizeRegExp(lst, key_name):
  """Sanitizes the given list to a valid regular expression.

  The 'lst' argument should be a list contains one or two string:
    * First string: The regular expression string.
    * Second string(optional): The flags of this regular expression.

  If it is not fits the rule above, the function will raise a FormatError.

  Args:
    lst: A list to be checked.
    key_name: The key name in the dict (For the error message).
  """
  if not (len(lst) in (1, 2) and all(isinstance(x, basestring) for x in lst)):
    raise FormatError('Value of %r is not a valid regular expression: %s' %
                      (key_name, lst))
  if len(lst) == 1:
    lst.append('')
