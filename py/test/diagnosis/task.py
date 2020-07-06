# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handles the operations on a task in the diagnosis tool.

Classes:
  * Task: Handles run/stop operations of a task.  When running a task, it will
      create a thread _run_steps_thread to run each step in this task.
  * _Step: A super class for all kinds of steps.  It handles start/stop
      operations.
  * _ConfirmStep: A step to confirm something with the user.
  * _CommandStep: A step to run a Linux command.
  * _FinallyStep: A step to run a Linux command,  this step will always be
      executed even user aborts the task.
"""

import os
import signal
import subprocess
import threading
import time

from cros.factory.test.diagnosis import common
from cros.factory.utils import process_utils

_WAIT_TIMEOUT = 0.1


class _STEP_STATE:
  """Enumeration of the states of a step."""
  SUCCESS = 'success'
  FAILED = 'failed'
  STOPPED = 'stopped'


class Task:
  """A task in the diagnosis tool.

  Attributes:
    _ui_proxy: Instance of DiagnosisToolUIProxy.
    _name: Name of the task.
    _description: Description text of the task.
    _state: Enum TASK_STATE.
    _inputs: A dict which key is the var_id of the input element and the value
        is the corresponding input element.
    _steps: A list of steps.
    _run_steps_thread: A thread to run all the commands.  None means this task
        is not running now.
    _stopping_lock: A lock to prevent user from stopping the task multiple times
    _current_step: The current running step.
  """

  def __init__(self, ui_proxy, config):
    """Task constructor.

    Args:
      ui_proxy: Instance of DiagnosisToolUIProxy.
      config: Sanitized config of this task.
    """
    runnable = (common.TOKEN.STEPS in config)
    self._ui_proxy = ui_proxy
    self._name = config[common.TOKEN.NAME]
    self._description = config[common.TOKEN.DESCRIPTION]
    self._state = (common.TASK_STATE.IDLE
                   if runnable else common.TASK_STATE.NOT_APPLICABLE)
    self._inputs = {}
    self._steps = []
    self._run_steps_thread = None
    self._stopping_lock = threading.Lock()
    self._current_step = None
    if runnable:
      inputs = config[common.TOKEN.INPUTS]
      for input_element in inputs:
        self._inputs[input_element[common.TOKEN.VAR_ID]] = input_element
      for step_element in config[common.TOKEN.STEPS]:
        if common.TOKEN.CONFIRM in step_element:
          step = _ConfirmStep(step_element[common.TOKEN.TITLE],
                              step_element[common.TOKEN.CONFIRM],
                              step_element[common.TOKEN.OPTIONS],
                              step_element[common.TOKEN.TIMEOUT],
                              step_element[common.TOKEN.EXPECTED_OUTPUT],
                              self._ui_proxy.Confirm,
                              self._ui_proxy.ConfirmStop)
        elif common.TOKEN.COMMAND in step_element:
          step = _CommandStep(step_element[common.TOKEN.COMMAND],
                              step_element[common.TOKEN.EXPECTED_OUTPUT],
                              step_element[common.TOKEN.TERMINATE_TIMEOUT],
                              step_element[common.TOKEN.TERMINATING_TIMEOUT],
                              step_element[common.TOKEN.ERROR_MESSAGE],
                              self._ui_proxy.AppendOutput)
        elif common.TOKEN.FINALLY in step_element:
          step = _FinallyStep(step_element[common.TOKEN.FINALLY],
                              step_element[common.TOKEN.EXPECTED_OUTPUT],
                              step_element[common.TOKEN.TERMINATE_TIMEOUT],
                              step_element[common.TOKEN.TERMINATING_TIMEOUT],
                              step_element[common.TOKEN.ERROR_MESSAGE],
                              self._ui_proxy.AppendOutput)
        self._steps.append(step)

  @property
  def name(self):
    return self._name

  @property
  def description(self):
    return self._description

  @property
  def inputs(self):
    return list(self._inputs.values())

  @property
  def state(self):
    return self._state

  @state.setter
  def state(self, new_state):
    self._state = new_state
    self._ui_proxy.SetState(new_state)

  def Start(self, input_values):
    """Starts the task.

    It will check whether the input values are all valid and then run the thread
    _RunSteps to run each step.

    Args:
      input_values: Input values from UI.
    """
    try:
      checked_input_values = self._CheckInputsValid(input_values)
    except common.FormatError as e:
      self._ui_proxy.AppendOutput('%s\n' % e)
      return

    with self._stopping_lock:
      if self._run_steps_thread is None:
        self._run_steps_thread = process_utils.StartDaemonThread(
            target=self._RunSteps, args=(checked_input_values,))

  def Stop(self):
    """Stops the task."""
    with self._stopping_lock:
      if self._run_steps_thread is not None:
        self.state = common.TASK_STATE.STOPPING
        if self._current_step is not None:
          self._current_step.Stop()

  def _CheckInputsValid(self, input_values):
    """Checks whether all the input values are valid.

    If there are missing input values (which will occure when the corresponding
    input fields in UI is disabled), this function will also fill it an empty
    string.

    Args:
      input_values: Input values.

    Returns:
      input values with missing values begin filled.
    """
    ret = {}
    for var_id in self._inputs:
      js_var_id = str(var_id)
      if js_var_id not in input_values:
        ret[var_id] = ''
      else:
        value = input_values[js_var_id]
        input_element = self._inputs[var_id]
        if (input_element[common.TOKEN.TYPE] == common.INPUT_TYPE.STRING and
            input_element[common.TOKEN.REGEXP] is not None):
          (regexp, flags) = tuple(input_element[common.TOKEN.REGEXP])
          if not common.CreateRegExp(regexp, flags).search(value):
            raise common.FormatError(
                'Invalid input field "%s%s", %r not matched (%r, %r)' %
                (input_element[common.TOKEN.PROMPT], value, value, regexp,
                 flags))
        ret[var_id] = value
    return ret

  def _RunSteps(self, inputs):
    """Runs all the steps.

    Args:
      inputs: Sanitized input values from UI.
    """
    with self._stopping_lock:
      if self.state != common.TASK_STATE.STOPPING:
        self.state = common.TASK_STATE.RUNNING

    success = True
    for step in self._steps:
      with self._stopping_lock:
        if (not step.MUST_BE_RUN and (self.state != common.TASK_STATE.RUNNING or
                                      not success)):
          continue
        self._current_step = step
        self._current_step.Init()
      step_state = self._current_step.Run(inputs)
      self._current_step = None
      if step_state != _STEP_STATE.SUCCESS:
        success = False

    with self._stopping_lock:
      if self.state == common.TASK_STATE.RUNNING:
        self.state = (common.TASK_STATE.DONE
                      if success else common.TASK_STATE.FAILED)
      elif self.state == common.TASK_STATE.STOPPING:
        self.state = common.TASK_STATE.STOPPED
      self._run_steps_thread = None


class _Step:
  """Super class of each kind of step."""
  MUST_BE_RUN = False

  def __init__(self):
    pass

  def Init(self):
    """Initializes this step before it starts to run."""

  def Run(self, *unused_args):
    """Runs this step."""

  def Stop(self):
    """Stops this step."""


class _ConfirmStep(_Step):
  """A step for confirm dialog.

  Attributes:
    _title: Title string of the dialog window.
    _content: Content string of the dialog.
    _options: List of strings, which are acceptable options.
    _timeout: Timeout (None means there is no timeout).
    _default_option: The option to be selected automatically if timeout.
    _expected_output: One of the options.  Whether this confirm is successful or
        not depends on whether the selected option is the same as
        expected_output.
    _confirm_id: Identify number of the confirm dialog.
    _selected_option: The option user selected.  It may be None because the
        confirm be stopped.
    _ending_notify: A condition variable to tell the main loop the confirm
        is finished (either user stops it or user selects a option).
    _ui_start_confirm: A function to tell the UI to show the confirm dialog.
    _ui_stop_confirm: A function to tell the UI to close the confirm dialog.
  """
  MUST_BE_RUN = False

  def __init__(self, title, content, options, timeout, expected_output,
               ui_start_confirm, ui_stop_confirm):
    super(_ConfirmStep, self).__init__()
    self._title = title
    self._content = content
    self._options = options
    self._timeout = None
    self._default_option = None
    self._expected_output = expected_output
    self._confirm_id = None
    self._selected_option = None
    self._ending_notify = None
    self._ui_start_confirm = ui_start_confirm
    self._ui_stop_confirm = ui_stop_confirm
    if timeout:
      self._timeout, self._default_option = tuple(timeout)

  def Init(self):
    self._selected_option = None
    self._ending_notify = threading.Condition()
    self._ending_notify.acquire()

  def Run(self, *unused_args):
    self._confirm_id = self._ui_start_confirm(
        title=self._title,
        content=self._content,
        options=self._options,
        timeout=self._timeout,
        default_option=self._default_option,
        callback=self._CallbackSelected)
    self._ending_notify.wait()
    if self._selected_option is None:
      ret = _STEP_STATE.STOPPED
    elif self._selected_option == self._expected_output:
      ret = _STEP_STATE.SUCCESS
    else:
      ret = _STEP_STATE.FAILED
    self._ending_notify.release()
    return ret

  def Stop(self):
    self._ending_notify.acquire()
    self._ui_stop_confirm(self._confirm_id)
    self._ending_notify.notify()
    self._ending_notify.release()

  def _CallbackSelected(self, option):
    """A callback function, called after user selects a option.

    Args:
      option: Selected option.
    """
    self._ending_notify.acquire()
    self._selected_option = option
    self._ending_notify.notify()
    self._ending_notify.release()


class _CommandStep(_Step):
  """A step for running a Linux command.

  After starting to run, it will create another two threads:
    stdout_caputurer: Captures the stdout text of the command.
    stderr_caputurer: Captures the stderr text of the command.

  When timeout or the user wants to stop the command, it will try to send
  SIGTERM to the command and wait for a period of time (terminating_timeout).
  If the command still exists after a period of time, the _CommandStep will
  send SIGKILL to kill the command process.

  Attributes:
    _command: Command line string.
    _expected_output: For deciding whether the command is successful or not
        after the command finished.
    _terminate_timeout: Timeout to stop this command after starting.
    _terminating_timeout: Timeout to kill this command after trying to stop.
    _error_message: The message to show if the command failed.
    _ui_append_output: A callback function for appending text to the UI.
    _need_to_stop: A boolean flag indicate whether the command should be
        stopped.
    _stdout_text: A string to store the stdout of the command if needs.
  """
  MUST_BE_RUN = False

  def __init__(self, command, expected_output,
               terminate_timeout, terminating_timeout, error_message,
               ui_append_output):
    super(_CommandStep, self).__init__()
    self._command = command
    self._expected_output = expected_output
    self._terminate_timeout = terminate_timeout
    self._terminating_timeout = terminating_timeout
    self._error_message = error_message
    self._ui_append_output = ui_append_output
    self._need_to_stop = False
    self._stdout_text = None

  def _AppendStdout(self, text):
    """Callback function, will be called when there is new stdout text.

    Args:
      text: New stdout text.
    """
    self._stdout_text += text

  def Init(self):
    self._need_to_stop = False

  def Run(self, *args):
    input_values = args[0]
    command = _ParseCommandLine(self._command, input_values)
    self._ui_append_output('$%s\n' % command)
    # start_new_session=True so setsid() will be invoked in the child processes,
    # for enabling sending a signal to all the process in the group.
    proc = subprocess.Popen(command, shell=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)
    output_list = [self._ui_append_output]
    if self._expected_output is not None:
      self._stdout_text = ''
      output_list += [self._AppendStdout]
    stdout_capturer = process_utils.StartDaemonThread(
        target=_PipeCapturer, args=(proc.stdout, output_list))
    stderr_capturer = process_utils.StartDaemonThread(
        target=_PipeCapturer, args=(proc.stderr, [self._ui_append_output]))
    # Waits until the command is finished, timeout is triggered, or user
    # requests to stop it.
    time_sum = 0
    while not self._need_to_stop:
      if proc.poll() is not None:
        break
      time.sleep(_WAIT_TIMEOUT)
      time_sum += _WAIT_TIMEOUT
      if (self._terminate_timeout is not None and
          time_sum > self._terminate_timeout):
        self._need_to_stop = True
    # Stops the process if it still exists after waiting for-loop.
    if proc.poll() is None:
      # Try to send SIGTERM first.
      try:
        os.killpg(proc.pid, signal.SIGTERM)
      except Exception:
        pass
      time_sum = 0
      while proc.poll() is None:
        time.sleep(_WAIT_TIMEOUT)
        time_sum += _WAIT_TIMEOUT
        if (self._terminating_timeout is not None and
            time_sum > self._terminating_timeout):
          break
      # Try to send SIGKILL if it still exists after timeout.
      if proc.poll() is None:
        try:
          os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
          pass
        proc.wait()
    stdout_capturer.join()
    stderr_capturer.join()
    if self._need_to_stop:
      return _STEP_STATE.STOPPED
    if self._CheckCommandSuccess(proc.returncode, self._stdout_text,
                                 self._expected_output):
      return _STEP_STATE.SUCCESS
    return _STEP_STATE.FAILED

  def Stop(self):
    self._need_to_stop = True

  @staticmethod
  def _CheckCommandSuccess(return_code, stdout_text, expected_output):
    """Check whether the command was finished successfully or not.

    Args:
      return_code: Return code of the process.
      stdout_text: Stdout text of the process.
      expected_output: Expected output of the process, there is three case:
        case 1, None: Whether the command is successful depends on the return
            code.
        case 2, string: Whether the command is successful depends on the whether
            stdout is the same as the string.
        case 3, a list: Whether the command is successful depends on the whether
            stdout is matched to the specified regular expression created by
            CreateRegExp(list).

    Returns:
      Boolean value indicate whether the command is successful or not.
    """
    if expected_output is None:
      return return_code == 0
    if isinstance(expected_output, str):
      return stdout_text == expected_output
    if isinstance(expected_output, list):
      (regexp, flags) = tuple(expected_output)
      return common.CreateRegExp(regexp, flags).search(stdout_text) is not None
    raise TypeError(
        "expected_output can't be of type %s" % type(expected_output))


class _FinallyStep(_CommandStep):
  """A step for finally.

  This kind of step is very similar to _CommandStep except that this one cannot
  be stopped.
  """
  MUST_BE_RUN = True

  def Stop(self):
    pass


def _PipeCapturer(pipe, callback_list):
  """Captures text from the pipe.

  Each time it capture one line from the pipe, it will call each function in
  callback_list with argument being that one line text (with newline character).

  Args:
    pipe: Pipe.
    callback_list: A list contains functions.
  """
  for line in iter(pipe.readline, b''):
    for func in callback_list:
      func(line)
  pipe.close()


def _ParseCommandLine(command, input_values):
  r"""Parses a command line string.

  It will:
    * replace $N (N is a number) with input_values[N]
    * replace $* with $1  $2  $3  ...
    * replace $@ with "$1"  "$2"  "$3"  ...  (this one is different from bash)
    * replace \$ with $
    * replace \\ with \
    * replace " with \" in input_values

  Args:
    cmd_line: Command line string.
    input_values: A dict contains the input values.

  Return:
    A command line string which is parsed.
  """
  ret = command
  ret = ret.replace('\\\\', '<splash!!>')
  ret = ret.replace('\\$', '<dollar!!>')
  dollar_star = ''
  dollar_at = ''
  splitter = ''
  for key, value in input_values.items():
    value.replace('"', '\\"')
    dollar_star += splitter + value
    dollar_at += splitter + '"' + value + '"'
    splitter = ' '
    ret = ret.replace('$%d' % int(key), value)
  ret = ret.replace('$*', dollar_star)
  ret = ret.replace('$@', dollar_at)
  ret = ret.replace('<splash!!>', '\\')
  ret = ret.replace('<dollar!!>', '$')
  return ret
