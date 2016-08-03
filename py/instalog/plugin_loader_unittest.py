#!/usr/bin/python2
#
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for Instalog plugin loader."""

# TODO(kitching): Currently we have no way of testing plugins that import
#                 other modules from their own directory.  For example:
#                 instalog/plugins/input_cool/input_cool.py
#                 instalog/plugins/input_cool/coll_utils.py
#                 Using the current testing method, this is not possible to
#                 test.  input_cool will use a fully-qualified instalog.* path
#                 to import its cool_utils, which will fail since _plugin_prefix
#                 sets the plugins directory to a separate path from
#                 py/instalog.  Come up with a better way of testing plugins
#                 that fall under this case.

from __future__ import print_function

import logging
import os
import shutil
import sys
import tempfile
import textwrap
import unittest

import instalog_common  # pylint: disable=W0611
from instalog import log_utils
from instalog import plugin_base
from instalog import plugin_loader


class TestPluginLoader(unittest.TestCase):

  _plugin_dir = None

  def setUp(self):
    """Creates and injects our temporary plugin directory into sys.path."""
    self._plugin_dir = tempfile.mkdtemp(prefix='plugin_sandbox_unittest.')
    sys.path.insert(0, self._plugin_dir)

  def tearDown(self):
    """Unloads and deletes the temporary plugin directory."""
    self.assertEqual(self._plugin_dir, sys.path.pop(0))
    shutil.rmtree(self._plugin_dir)

  def _createPluginFile(self, content):
    """Creates a plugin in the temporary directory on disk.

    Returns:
      Name of the plugin file.
    """
    fd, fpath = tempfile.mkstemp(dir=self._plugin_dir, suffix='.py')
    with os.fdopen(fd, 'w') as f:
      f.write(textwrap.dedent(content))
    return os.path.splitext(os.path.basename(fpath))[0]

  def testInvalidPluginAPI(self):
    """Tests that a loader passed an invalid PluginAPI object will complain."""
    with self.assertRaisesRegexp(TypeError, 'Invalid PluginAPI object'):
      plugin_loader.PluginLoader('plugin_id', plugin_api=True)

  def testLoad(self):
    """Tests getting an instance of a plugin from a module."""
    pname = self._createPluginFile(
        '''\
        import instalog_common  # pylint: disable=W0611
        from instalog import plugin_base
        class InputTest(plugin_base.InputPlugin):
          pass
        ''')

    # Should succeed with correct superclass=InputPlugin.
    pe = plugin_loader.PluginLoader(pname, pname, plugin_base.InputPlugin,
                                    {}, plugin_api=None, _plugin_prefix='')
    self.assertIsInstance(pe.Create(), plugin_base.InputPlugin)

    # Should fail with incorrect superclass=InputPlugin.
    pe = plugin_loader.PluginLoader(pname, pname, plugin_base.OutputPlugin,
                                    {}, plugin_api=None, _plugin_prefix='')
    with self.assertRaisesRegexp(
        plugin_base.LoadPluginError, r'contains 0 plugin classes'):
      pe.Create()

  def testSyntaxError(self):
    """Tests loading a plugin with a syntax error."""
    pname = self._createPluginFile('/')
    pe = plugin_loader.PluginLoader(pname, pname, _plugin_prefix='')
    with self.assertRaisesRegexp(
        plugin_base.LoadPluginError, r'SyntaxError: invalid syntax'):
      pe.Create()

  def testRuntimeInitArgsError(self):
    """Tests loading a plugin with a runtime error: __init__ args."""
    pname = self._createPluginFile(
        '''\
        import instalog_common  # pylint: disable=W0611
        from instalog import plugin_base
        class InputTest(plugin_base.InputPlugin):
          def __init__(self):
            pass
        ''')
    pe = plugin_loader.PluginLoader(pname, pname, _plugin_prefix='')
    with self.assertRaisesRegexp(
        plugin_base.LoadPluginError, r'TypeError: __init__\(\) takes'):
      pe.Create()

  def testRuntimeInitMethodError(self):
    """Tests loading a plugin with a runtime error: within __init__."""
    pname = self._createPluginFile(
        '''\
        import instalog_common  # pylint: disable=W0611
        from instalog import plugin_base
        class InputTest(plugin_base.InputPlugin):
          def __init__(self, *args, **kwargs):
            1 / 0
        ''')
    pe = plugin_loader.PluginLoader(pname, pname, _plugin_prefix='')
    with self.assertRaisesRegexp(
        plugin_base.LoadPluginError, r'ZeroDivisionError: integer division'):
      pe.Create()

  def testArgsInvalidError(self):
    """Tests providing invalid arguments to a plugin."""
    pname = self._createPluginFile(
        '''\
        import instalog_common  # pylint: disable=W0611
        from instalog import plugin_base
        from instalog.utils.arg_utils import Arg
        class InputTest(plugin_base.InputPlugin):
          ARGS = [
            Arg('explode', bool, 'True if device is expected to explode'),
          ]
        ''')
    # Invalid, since `explode` is a required argument.
    pe = plugin_loader.PluginLoader(pname, _plugin_prefix='')
    with self.assertRaisesRegexp(
        plugin_base.LoadPluginError,
        r'Error parsing arguments: Required argument explode'):
      pe.Create()

  def testArgs(self):
    """Tests providing valid arguments to a plugin."""
    pname = self._createPluginFile(
        '''\
        import instalog_common  # pylint: disable=W0611
        from instalog import plugin_base
        from instalog.utils.arg_utils import Arg
        class InputTest(plugin_base.InputPlugin):
          ARGS = [
            Arg('explode', bool, 'True if device is expected to explode'),
          ]
        ''')
    pe = plugin_loader.PluginLoader(
        pname, config={'explode': True}, _plugin_prefix='')
    self.assertIsInstance(pe.Create(), plugin_base.InputPlugin)


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG, format=log_utils.LOG_FORMAT)
  unittest.main()
