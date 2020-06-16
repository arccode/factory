# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Sanitizes the YAML configs."""

import collections
import copy
import re

from cros.factory.test.diagnosis import common
from cros.factory.utils import process_utils

_DEFAULT_INPUT_BOOL_VALUE = True
_DEFAULT_INPUT_FILE_PATTERN = '.*'
_DEFAULT_INPUT_FILE_TYPE = 'regular-file'

_DEFAULT_CONFIRM_TITLE = 'Confirm'
_DEFAULT_CONFIRM_OPTIONS = (common.OPTIONS.YES, common.OPTIONS.CANCEL)
_DEFAULT_CONFIRM_TIMEOUT = (10, common.OPTIONS.YES)
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
    raise common.FormatError('Value of the configurations is not a list')
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
  _SanitizeDefaultValueAndType(config, [
      (common.TOKEN.NAME, '', str),
      (common.TOKEN.DESCRIPTION, '', str)])
  try:
    if common.TOKEN.STEPS in config:
      if not isinstance(config[common.TOKEN.STEPS], list):
        raise common.FormatError('Value of %r is not a %r' %
                                 (common.TOKEN.STEPS, 'list'))
      config[common.TOKEN.STEPS] = [_SanitizeStep(x)
                                    for x in config[common.TOKEN.STEPS]]
      _SanitizeDefaultValueAndType(config, [(common.TOKEN.INPUTS, [], list)])
      config[common.TOKEN.INPUTS] = _SanitizeInputs(config[common.TOKEN.INPUTS])
    if common.TOKEN.MEMBER in config:
      if not isinstance(config[common.TOKEN.MEMBER], list):
        raise common.FormatError('Value of %r is not a %r' %
                                 (common.TOKEN.MEMBER, 'list'))
      config[common.TOKEN.MEMBER] = [_SanitizeTask(x)
                                     for x in config[common.TOKEN.MEMBER]]
      count = collections.Counter(x[common.TOKEN.NAME]
                                  for x in config[common.TOKEN.MEMBER])
      repeat_names = [x for x in count if count[x] > 1]
      for repeat_name in repeat_names:
        raise common.FormatError('Same sub-task name: %r' % repeat_name)
    return config
  except common.FormatError as e:
    raise common.FormatError(config[common.TOKEN.NAME] + ':' + str(e))


def _SanitizeInputs(configs):
  """Validates inputs and sets default value for missing fields.

  It will sanitize each input element in it and then fill up the missing var_id.
  """
  configs = [_SanitizeInput(x) for x in configs]
  num_ids = [x[common.TOKEN.VAR_ID]
             for x in configs if x[common.TOKEN.VAR_ID] is not None]
  id_max = max(num_ids) if num_ids else 0
  for config in configs:
    if config[common.TOKEN.VAR_ID] is None:
      id_max += 1
      config[common.TOKEN.VAR_ID] = id_max
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
        (common.TOKEN.PROMPT, '', str),
        (common.TOKEN.HELP, '', str),
        (common.TOKEN.VAR_ID, None, (type(None), int))])
    config_type = config[common.TOKEN.TYPE].lower()
    if config_type in (common.INPUT_TYPE.NUMBER, common.INPUT_TYPE.SLIDER):
      _SanitizeInputNumberAndSlider(config)

    elif config_type == common.INPUT_TYPE.CHOICES:
      _SanitizeInputChoices(config)

    elif config_type == common.INPUT_TYPE.BOOL:
      _SanitizeInputBool(config)

    elif config_type == common.INPUT_TYPE.FILE:
      _SanitizeInputFile(config)

    elif config_type == common.INPUT_TYPE.STRING:
      _SanitizeInputString(config)

    else:
      raise common.FormatError('Unknown input type: %r.' % config_type)

  except KeyError as e:
    raise common.FormatError('Key "%s" not found in the input element.' % e)
  except Exception as e:
    raise common.FormatError('Exception: "' + str(e) + '"')
  return config


def _SanitizeInputNumberAndSlider(ref):
  for key in [common.TOKEN.MIN, common.TOKEN.MAX, common.TOKEN.STEP]:
    if isinstance(ref[key], (int, float)):
      pass
    elif isinstance(ref[key], str) and ref[key].startswith('!'):
      ref[key] = _GetCommandOutput(ref[key][1:], float, 'float')
    else:
      raise common.FormatError(
          'Value of %r is neither a number nor a command: %r' % (key, ref[key]))
  _SanitizeDefaultValueAndType(ref, [
      (common.TOKEN.VALUE, ref[common.TOKEN.MIN], (int, float)),
      (common.TOKEN.ROUND, 0, (int, float)),
      (common.TOKEN.UNIT, '', str)])


def _SanitizeInputChoices(ref):
  key = common.TOKEN.CHOICES
  if isinstance(ref[key], list):
    pass
  elif isinstance(ref[key], str) and ref[key].startswith('!'):
    ref[key] = _GetCommandOutput(ref[key][1:], lambda x: re.split(' |\t|\n', x))
  else:
    raise common.FormatError(
        'Value of %r is neither a number nor a command: %r' % (key, ref[key]))
  ref[key] = [str(x) for x in ref[key] if str(x)]
  if not ref[key]:
    raise common.FormatError('No valid flag in %r.' % key)
  ref.setdefault(common.TOKEN.VALUE, ref[key][0])
  if ref[common.TOKEN.VALUE] not in ref[key]:
    raise common.FormatError('Default value is not a valid flag: %r.' %
                             ref[common.TOKEN.VALUE])


def _SanitizeInputBool(ref):
  _SanitizeDefaultValueAndType(ref, [
      (common.TOKEN.VALUE, _DEFAULT_INPUT_BOOL_VALUE, bool),
      (common.TOKEN.ENABLE_LIST, [], list),
      (common.TOKEN.DISABLE_LIST, [], list)])


def _SanitizeInputFile(ref):
  _SanitizeDefaultValueAndType(ref, [
      (common.TOKEN.PATTERN, _DEFAULT_INPUT_FILE_PATTERN, str),
      (common.TOKEN.FILE_TYPE, _DEFAULT_INPUT_FILE_TYPE, str)])


def _SanitizeInputString(ref):
  _SanitizeDefaultValueAndType(ref, [
      (common.TOKEN.VALUE, '', str),
      (common.TOKEN.REGEXP, None, (type(None), list)),
      (common.TOKEN.HINT, '', str)])
  if isinstance(ref[common.TOKEN.REGEXP], list):
    _SanitizeRegExp(ref[common.TOKEN.REGEXP], common.TOKEN.REGEXP)


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
      case 3, A list like [string1, string2]:
        Like case 2, but use regular expression (string1 is the expression,
        string2 is the re flags).

  Args:
    config: Step element.

  Returns:
    A sanitized step element.
  """
  found = 0
  if common.TOKEN.CONFIRM in config:
    if not isinstance(config[common.TOKEN.CONFIRM], str):
      raise common.FormatError('A confirm content must be a string')
    _SanitizeDefaultValueAndType(config, [
        (common.TOKEN.TITLE, _DEFAULT_CONFIRM_TITLE, str),
        (common.TOKEN.OPTIONS, list(_DEFAULT_CONFIRM_OPTIONS), list),
        (common.TOKEN.TIMEOUT, list(_DEFAULT_CONFIRM_TIMEOUT),
         (list, type(None)))])
    if not config[common.TOKEN.OPTIONS]:
      raise common.FormatError('No options for user to select.')
    config.setdefault(common.TOKEN.EXPECTED_OUTPUT,
                      config[common.TOKEN.OPTIONS][0])
    if config[common.TOKEN.EXPECTED_OUTPUT] not in config[common.TOKEN.OPTIONS]:
      raise common.FormatError('expected_output not in the options: %r' %
                               config[common.TOKEN.EXPECTED_OUTPUT])
    found += 1
  for key in (
      x for x in [common.TOKEN.COMMAND, common.TOKEN.FINALLY] if x in config):
    if not isinstance(config[key], str):
      raise common.FormatError('A linux shell command must be a string')
    _SanitizeDefaultValueAndType(config, [
        (common.TOKEN.TERMINATE_TIMEOUT, None, (int, type(None))),
        (common.TOKEN.TERMINATING_TIMEOUT, None, (int, type(None))),
        (common.TOKEN.EXPECTED_OUTPUT, None, (type(None), str, list)),
        (common.TOKEN.ERROR_MESSAGE, None, (type(None), str))])
    if isinstance(config[common.TOKEN.EXPECTED_OUTPUT], list):
      _SanitizeRegExp(config[common.TOKEN.EXPECTED_OUTPUT],
                      common.TOKEN.EXPECTED_OUTPUT)
    found += 1
  if found != 1:
    raise common.FormatError('Unknown step type %r.' % config)
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
    output = process_utils.SpawnOutput(command, shell=True)
  except Exception as e:
    raise common.FormatError('Runs command %r failed, reason %r' % (command, e))
  try:
    return converter(output)
  except Exception as e:
    raise common.FormatError('Cannot convert the output of %r to %s: %s' %
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
      raise common.FormatError('Value of %r is not a %r' % (key, value_type))


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
  if not (len(lst) in (1, 2) and all(isinstance(x, str) for x in lst)):
    raise common.FormatError(
        'Value of %r is not a valid regular expression: %s' % (key_name, lst))
  if len(lst) == 1:
    lst.append('')
