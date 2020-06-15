# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re


class INPUT_TYPE:
  """Enumeration the type of the input field for user to input data."""
  BOOL = 'bool'
  CHOICES = 'choices'
  FILE = 'file'
  NUMBER = 'number'
  SLIDER = 'slider'
  STRING = 'string'


class TASK_STATE:
  """Enumeration of state of the current task."""
  IDLE = 'idle'
  RUNNING = 'running'
  DONE = 'done'
  FAILED = 'failed'
  STOPPING = 'stopping'
  STOPPED = 'stopped'
  NOT_APPLICABLE = 'not-applicable'


_ACCEPTABLE_RE_FLAGS = set('ILMSUX')


class TOKEN:
  """Enumeration of the keys of the YAML configs."""
  CHOICES = 'choices'
  COMMAND = 'command'
  CONFIRM = 'confirm'
  DESCRIPTION = 'description'
  DISABLE_LIST = 'disable_list'
  ENABLE_LIST = 'enable_list'
  ERROR_MESSAGE = 'error_message'
  EXPECTED_OUTPUT = 'expected_output'
  FILE_TYPE = 'file_type'
  FINALLY = 'finally'
  HELP = 'help'
  HINT = 'hint'
  TASK_ID = 'task_id'
  INPUTS = 'inputs'
  MAX = 'max'
  MEMBER = 'member'
  MIN = 'min'
  NAME = 'name'
  OPTIONS = 'options'
  PATTERN = 'pattern'
  PROMPT = 'prompt'
  REGEXP = 'regexp'
  ROUND = 'round'
  STEP = 'step'
  STEPS = 'steps'
  TERMINATE_TIMEOUT = 'terminate_timeout'
  TERMINATING_TIMEOUT = 'terminating_timeout'
  TIMEOUT = 'timeout'
  TITLE = 'title'
  TYPE = 'type'
  UNIT = 'unit'
  VALUE = 'value'
  VAR_ID = 'var_id'


class BACKEND_EVENTS:
  """Enumeration of the events which are Backend -> Frontend."""
  APPEND_OUTPUT = 'appendOutput'  # Appends some text to the console output.
  CLEAR_OUTPUT = 'clearOutput'  # Clears the console output.
  CONFIRM_DIALOG = 'confirmDialog'  # Shows a confirm dialog.
  CONFIRM_DIALOG_STOP = 'confirmDialogStop'  # Closes a confirm dialog.
  LOAD_TASK = 'loadTask'  # Loads a task.
  SET_DESCRIPTION = 'setDescription'  # Sets the description field in UI.
  SET_INPUTS = 'setInputs'  # Sets the input field in UI.
  SET_MENU = 'setMenu'  # Sets the menu of the tasks in UI.
  SET_NAME = 'setName'  # Sets the name field in UI.
  SET_STATE = 'setState'  # Sets the state field in UI.


class OPTIONS:
  """Some options in the confirm dialog."""
  YES = 'Yes'
  CANCEL = 'Cancel'

  # When user wants to load another task while the current task is running, we
  # need to tell them that they should stop the running task first.
  STOP_IT = 'OK, stop it'
  KEEP_IT = 'No, keep it running'


def CreateRegExp(string, flags):
  """Creates a regular expression object.

  Args:
    string: Regular expression.
    flags: A string with flag each character.  Acceptable character:
        I, L, M, S, U, X.
        For example, "IL" means re.I | re.L

  Return:
    A regular expression object.
  """
  flag_num = 0
  for c in flags.upper():
    if c in _ACCEPTABLE_RE_FLAGS:
      flag_num |= getattr(re, c)
  return re.compile(string, flag_num)


class FormatError(Exception):
  pass
