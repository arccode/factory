# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Diagnosis Tool backend.

Classes:
  * DiagnosisToolRPC: Handles all the frontend -> backend events.
  * DiagnosisToolUIProxy: Handles all the backend -> frontend events.
  * _ConfirmEventRegister: Remembers all the callback functions (which should be
      called after user selects an option in UI) of the confirm dialogs so that
      DiagnosisToolUIProxy will no need to tell DiagnosisToolRPC which callback
      function to be called after user selected an option (UIProxy tells it
      the callback function and RPC asks it for the callback function).

Notes:
  1. The YAML configs will be imported after the UI window is initialized.
"""

import logging
import os
import threading

import yaml

from cros.factory.test.diagnosis import common
from cros.factory.test.diagnosis import sanitizer
from cros.factory.test.diagnosis import task
from cros.factory.test import event

_BASE_PATH = os.path.dirname(os.path.abspath(__file__))


class _ConfirmEventRegister:
  """Stores the confirm events and its callback function.

  Attributes:
    _register_counter: A monotonically-increasing counter for the id of the
        confirm event.
    _callback_func: A dict to store the callback functions which should be
        called after user selects a option in the confirm dialog in UI.  The
        keys and values of it are defined below:
      key: The identify number of the confirm dialog.
      value: A tuple with three elements:
        first element: The callback function.
        second element: The extra arguemnts for the callback function.
        third element: The extra keyword-arguments for the callback function.
  """

  def __init__(self):
    """Constructor."""
    self._register_counter = 0
    self._callback_func = {}

  def Register(self, callback, callback_args, callback_kwargs):
    """Registers a confirm event.

    The callback function will be called with the fist argument be the option
    which user selected.

    Args:
      callback: A callback function which should be called after a option be
          selected.
      callback_args: Extra arguments for the callback function.
      callback_kwargs: Extra keyword-arguments for the callback function.

    Returns:
      Idenitfy number of this confirm event.
    """
    args = callback_args if callback_args is not None else ()
    kwargs = callback_kwargs if callback_kwargs is not None else {}
    self._register_counter += 1
    identify_number = self._register_counter
    self._callback_func[identify_number] = (callback, args, kwargs)
    return identify_number

  def Remove(self, identify_number):
    """Removes a confirm event.

    Args:
      identify_number: The identify number of the confirm event to remove.
    """
    if identify_number in self._callback_func:
      del self._callback_func[identify_number]

  def Selected(self, identify_number, selected_option):
    """A callback function, will be called after a option be selected in UI.

    Args:
      identify_number: The identify number of the confirm dialog.
      selected_option: The option which was selected.
    """
    if identify_number in self._callback_func:
      func, args, kwargs = self._callback_func[identify_number]
      func(selected_option, *args, **kwargs)
      del self._callback_func[identify_number]


class DiagnosisToolUIProxy:
  """Handles the Backend -> Frontend events of the diagnosis tool.

  Class variables:
    _post_event_lock: For preventing the "_PostEvent()" be called twice at the
        same time.

  Attributes:
    _goofy_rpc: Instance of GoofyRPC.
    _confirm_event_register: Instance of _ConfirmEventRegister
  """
  _post_event_lock = threading.Lock()

  def __init__(self, goofy_rpc, confirm_event_register):
    self._goofy_rpc = goofy_rpc
    self._confirm_event_register = confirm_event_register

  def _PostEvent(self, event_type, **kwargs):
    """Posts a Diagnosis Tool Event.

    Args:
      event_type: The type of the event.
      kwargs: Other parameters to post.
    """
    with self._post_event_lock:
      self._goofy_rpc.PostEvent(
          event.Event(event.Event.Type.DIAGNOSIS_TOOL_EVENT,
                      sub_type=event_type,
                      **kwargs))

  def LoadTask(self, task_id):
    """Asks the UI to load the task.

    Args:
      task_id: Id of the task.
    """
    self._PostEvent(common.BACKEND_EVENTS.LOAD_TASK, task_id=task_id)

  def SetMenu(self, menu_config):
    """Sets the task menu in the UI.

    Args:
      menu_config: Config of the menu.
    """
    self._PostEvent(common.BACKEND_EVENTS.SET_MENU, menu=menu_config)

  def SetName(self, name):
    """Sets the task name in the UI.

    Args:
      name: Tasks name.
    """
    self._PostEvent(common.BACKEND_EVENTS.SET_NAME, name=name)

  def SetState(self, state):
    """Sets the state in UI.

    Args:
      state: The state.
    """
    self._PostEvent(common.BACKEND_EVENTS.SET_STATE, state=state)
    if state in (common.TASK_STATE.DONE,
                 common.TASK_STATE.FAILED,
                 common.TASK_STATE.STOPPED):
      self.AppendOutput('\n\n')

  def SetDescription(self, description):
    """Sets the description of the current task in UI.

    Args:
      description: Description text.
    """
    self._PostEvent(common.BACKEND_EVENTS.SET_DESCRIPTION,
                    description=description)

  def SetInputs(self, inputs):
    """Sets the input fields of the current task in UI.

    Args:
      inputs: Input elements.
    """
    self._PostEvent(common.BACKEND_EVENTS.SET_INPUTS, inputs=inputs)

  def AppendOutput(self, text):
    """Append some text to the console output in UI.

    Args:
      text: String which needs to be added to the output field.
    """
    self._PostEvent(common.BACKEND_EVENTS.APPEND_OUTPUT, text=text)

  def ClearOutput(self):
    """Clear the console output in UI."""
    self._PostEvent(common.BACKEND_EVENTS.CLEAR_OUTPUT)

  def Confirm(self, title, content, options, timeout, default_option,
              callback, callback_args=None, callback_kwargs=None):
    """Generates a confirm dialog for user to select something in UI.

    Args:
      title: Title string of the dialog window.
      content: Content of the dialog window.
      options: A list of strings.
      timeout: Timeout (None if there is no timeout).
      default_option: Default option to be selected.  It will be selected
          automatically if timeout.
      callback: Callback function to call when an option be selected.
      callback_args: Extra arguments of the callback function.
      callback_kwargs: Extra keyword-arguments of the callback function.

    Return:
      Identify number of the confirm dialog.
    """
    confirm_id = self._confirm_event_register.Register(callback,
                                                       callback_args,
                                                       callback_kwargs)
    self._PostEvent(common.BACKEND_EVENTS.CONFIRM_DIALOG,
                    id=confirm_id,
                    title=title, content=content, options=options,
                    timeout=timeout, default_option=default_option)
    return confirm_id

  def ConfirmStop(self, confirm_id):
    """Asks UI to stop and close a confirm dialog.

    Args:
      confirm_id: Identify number of the confirm dialog.
    """
    self._confirm_event_register.Remove(confirm_id)
    self._PostEvent(common.BACKEND_EVENTS.CONFIRM_DIALOG_STOP, id=confirm_id)


class DiagnosisToolRPC:
  """Handles the Frontend -> Backend rpc events.

  Attributes:
    _goofy_rpc: Instance of GoofyRPC.
    _confirm_event_register: Instance of _ConfirmEventRegister.
    _ui_proxy: Instance of DiagnosisToolUIProxy.
    _task_configs: A dictionary to store all the config of the tasks.
    _current_task: Current task.
    _current_task_id: Id of the current task.  The task is is coined by the
        pathname in YAML.
  """

  def __init__(self, goofy_rpc):
    """DiagnosisToolRPC constructor.

    Reads the configuration files.

    Args:
      goofy_rpc: GoofyRPC object to send the events to the GUI.
    """
    self._goofy_rpc = goofy_rpc
    self._confirm_event_register = _ConfirmEventRegister()
    self._ui_proxy = DiagnosisToolUIProxy(self._goofy_rpc,
                                          self._confirm_event_register)
    self._task_configs = {}
    self._current_task = None
    self._current_task_id = None

  def ShowWindow(self):
    """UI shows the diagnosis tool's main window."""
    all_configs = _ImportConfigFiles()
    (menu_config, self._task_configs) = _GetMenuAndTaskConfigs(all_configs)
    self._ui_proxy.SetMenu(menu_config)

  def InitTask(self, task_id):
    """Initializes a task.

    Args:
      task_id: Id of the task to be initialized.
    """
    self._current_task_id = task_id
    self._current_task = task.Task(self._ui_proxy,
                                   self._task_configs[self._current_task_id])
    self._ui_proxy.ClearOutput()
    self._ui_proxy.SetName(self._current_task.name)
    self._ui_proxy.SetState(self._current_task.state)
    self._ui_proxy.SetDescription(self._current_task.description)
    self._ui_proxy.SetInputs(self._current_task.inputs)

  def LoadTask(self, task_id):
    """Checks whether diagnosis tool can load another task now.

    If the current task is not running (done/failed/stopped), this function
    will post an event to ask UI to load task immediately.
    If not, it will tell the user that they need to stop the task first.

    Args:
      task_id: Id of the task that user want to load.

    Return:
      True if the backend will load another task immediately.
      False if not.
    """
    if task_id == self._current_task_id:
      return False
    if self._current_task is not None:
      if self._current_task.state == common.TASK_STATE.STOPPING:
        return False
      if self._current_task.state == common.TASK_STATE.RUNNING:
        self._ui_proxy.Confirm(title='Instruction',
                               content='You should stop the task first.',
                               options=[common.OPTIONS.STOP_IT,
                                        common.OPTIONS.KEEP_IT],
                               timeout=10,
                               default_option=common.OPTIONS.KEEP_IT,
                               callback=self._LoadTaskConfirmCallback)
        return False
    self._ui_proxy.LoadTask(task_id)
    return True

  def _LoadTaskConfirmCallback(self, option):
    """Callback function for the confirm event of the load task event.

    Args:
      option: Option user selected.
    """
    if option == common.OPTIONS.STOP_IT:
      self._current_task.Stop()

  def StartTask(self, task_id, inputs):
    """Starts to running the task.

    Args:
      task_id: Id of the current task.
      inputs: Inputs of the task.
    """
    if task_id != self._current_task_id:
      return
    if self._current_task.state == common.TASK_STATE.NOT_APPLICABLE:
      return
    self._current_task.Start(inputs)

  def StopTask(self, task_id):
    """Stops the current running task.

    Args:
      task_id: Id of the current task.
    """
    if task_id != self._current_task_id:
      return
    if self._current_task.state != common.TASK_STATE.RUNNING:
      return
    self._ui_proxy.Confirm(title='Confirm',
                           content=('Do you really want to stop the task %r?' %
                                    self._current_task.name),
                           options=[common.OPTIONS.YES, common.OPTIONS.CANCEL],
                           timeout=10,
                           default_option=common.OPTIONS.CANCEL,
                           callback=self._StopTaskConfirmCallback,
                           callback_args=(task_id,))

  def _StopTaskConfirmCallback(self, option, task_id):
    """A callback function for the user choosing to stop the task or not.

    Args:
      option: The option that user selected.
      task_id: Id of task.
    """
    if task_id != self._current_task_id:
      return
    if (option == common.OPTIONS.YES and
        self._current_task.state == common.TASK_STATE.RUNNING):
      self._current_task.Stop()

  def ConfirmSelected(self, confirm_id, option):
    """User selected a option in a confirm dialog.

    Args:
      confirm_id: Identify number of the confirm dialog.
      option: The option that the user selected.
    """
    self._confirm_event_register.Selected(confirm_id, option)


def _ImportConfigFiles():
  """Imports all the yaml config files.

  Return:
    The json format dict/list contains all the tasks.
  """
  all_configs = []
  for (dirpath, unused_dirnames, filenames) in os.walk(_BASE_PATH):
    for filename in (x for x in filenames if x[-5:] == '.yaml'):
      try:
        opened_file = open(os.path.join(dirpath, filename), 'r')
        new_configs = yaml.load(opened_file)
      except Exception:
        logging.exception('Cought an exception while reading and parsing '
                          'the yaml config file %r.', filename)
        raise
      if isinstance(new_configs, list):
        all_configs = all_configs + new_configs
      else:
        all_configs = all_configs + [new_configs]
  return sanitizer.SanitizeConfig(all_configs)


def _TaskPathToId(path):
  """Transforms the pathname in YAML to an id for a task.

  Args:
    path: Path name.

  Returns:
    id of the task.
  """
  return '<joiner>'.join(path)


def _GetMenuAndTaskConfigs(config):
  """Gets the task menu and a dict contain all the tasks from the config.

  It will trace the config and generate the meun config for UI and a dict
  contains all the tasks.

  The dict is defined below:
    key: task_id
    value: config of the task

  Args:
    config: Config.

  Returns:
    A tuple (menu_config, the_dict)
  """
  tasks = {}

  def Tracer(config, path):
    name = config[common.TOKEN.NAME]
    curr_path = path + [name]
    identify = _TaskPathToId(curr_path)
    tasks[identify] = config
    ret = {common.TOKEN.TASK_ID: identify, common.TOKEN.NAME: name}
    if common.TOKEN.MEMBER in config:
      ret[common.TOKEN.MEMBER] = [Tracer(x, curr_path)
                                  for x in config[common.TOKEN.MEMBER]]
    return ret
  menu = [Tracer(x, []) for x in config]
  return (menu, tasks)
