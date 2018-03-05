# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""LocalEnv (local environment data) is key value pairs saved in each thread.

For each thread, ``LocalEnv()`` returns a dictionary bound to current thread.
You can use ``SetLocalEnv()`` to override some entries in the dictionary, for
example::

  def PrintFoo():
    print LocalEnv().get('foo')

  def RunTask():
    with SetLocalEnv(foo=1):
      PrintFoo()  # 1
      with SetLocalEnv(foo=2):
        PrintFoo()  # 2
      PrintFoo()  # 1

As you can see, the value will be reverted when the program leaves the ``with``
context.

In most cases, you should just add an argument for function calls, instead of
using ``LocalEnv()``.  ``LocalEnv()`` is designed for variables that are thread
specific, and works like an option.  For example, the utility functions often
needs to know **which device this function should use**.  It could be the
station (``CreateStationInterface()``) or DUT (``CreateDUTInterface()``).  We
don't want to add arguments for all utility functions, so instead we can use
``LocalEnv()`` as::

  def SomeUtilityFunction():
    interface = LocalEnv().get('interface', DEFAULT_INTERFACE)
    # use ``interface`` to do the task
    # ...

  def Func():
    with SetLocalEnv(interface=CreateDUTInterface()):
      SomeUtilityFunction()  # will perform on DUT interface
    with SetLocalEnv(interface=CreateStationInterface()):
      SomeUtilityFunction()  # will perform on station interface
"""


import contextlib
import threading


_local_env = threading.local()


class LocalEnvException(Exception):
  """Exception for LocalEnv."""


def _InitLocalEnv():
  """Initialize the stack if it is not initialized yet."""
  if not hasattr(_local_env, 'stack'):
    _local_env.stack = [{}]


def LocalEnv():
  """Get a dictionary saved in current thread context."""
  _InitLocalEnv()
  return _local_env.stack[-1]


@contextlib.contextmanager
def SetLocalEnv(**kwargs):
  _InitLocalEnv()
  stack_size = len(_local_env.stack)
  new_env = _local_env.stack[-1].copy()
  new_env.update(kwargs)
  _local_env.stack.append(new_env)

  try:
    yield
  finally:
    if len(_local_env.stack) != stack_size + 1:
      raise LocalEnvException(
          'mismatched number of append and pop, expected: %d, actual: %d' % (
              stack_size + 1, len(_local_env.stack)))
    _local_env.stack.pop()
