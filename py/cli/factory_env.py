#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The tool to set factory env path properly and then run the command.

The tool sets py_pkg to the env path properly, so that cros.factory.* can be
located for the command. After env is set, it runs the command directly.
"""

import os
import sys


HELP_MSG = """
Usage :
    1. Make bin/xxx a symbolic link to py/cli/factory_env.py, and make
       py/cli/xxx.py a symbolic link to real script path.
    2. bin/factory_env program args...
       program can be a path to a excutable program, or any excutable program
       that can be found in $PATH.
"""


def GetFactoryDir():
  factory_env_path = os.path.realpath(__file__.replace('.pyc', '.py'))
  if os.path.exists(factory_env_path):
    # factory_env_path should be '.../factory/py/cli/factory_env.py'
    factory_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(factory_env_path)))
    return factory_dir

  raise RuntimeError(
      'cros.factory.cli.factory_env should not be executed from factory.par')


def GetRealScriptPath(tool_path):
  """Find real script path from a symlink.

  Args:
    tool_path: A path that is a symlink that links to py/cli/factory_env.py.
  """
  tool_name = os.path.basename(tool_path)
  return os.path.join(GetFactoryDir(), 'py/cli/', tool_name + '.py')


def ShowHelpAndExit():
  print(HELP_MSG, end='')
  sys.exit(1)


def Main():
  file_name = os.path.basename(sys.argv[0])
  while file_name == 'factory_env':
    # It means we are running "factory_env ...".
    sys.argv.pop(0)
    if not sys.argv:
      ShowHelpAndExit()
    file_name = os.path.basename(sys.argv[0])

  real_file_name = os.path.basename(os.path.realpath(sys.argv[0]))
  if real_file_name == 'factory_env.py':
    # It means that it's a symbolic link to factory_env.
    # We need to execute the file in py/cli/file_name.py.
    sys.argv[0] = GetRealScriptPath(sys.argv[0])

  # Set env path properly
  factory_dir = GetFactoryDir()
  child_env = dict(os.environ)
  child_env['PYTHONPATH'] = os.path.join(factory_dir, 'py_pkg')

  # Set locale to utf-8
  child_env['LC_ALL'] = 'en_US.UTF-8'

  # Execute it directly
  try:
    os.execvpe(sys.argv[0], sys.argv, env=child_env)
  except OSError:
    ShowHelpAndExit()


if __name__ == '__main__':
  Main()
