#!/usr/bin/env python3
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

import logging
import os
import shutil
import sys
import tempfile
import textwrap
import unittest

from cros.factory.instalog import log_utils
from cros.factory.instalog import plugin_base
from cros.factory.instalog import plugin_loader


# pylint: disable=protected-access
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
    with tempfile.NamedTemporaryFile(
        'w', dir=self._plugin_dir, suffix='.py', delete=False) as f:
      f.write(textwrap.dedent(content))
      return os.path.splitext(os.path.basename(f.name))[0]

  def testInvalidPluginAPI(self):
    """Tests that a loader passed an invalid PluginAPI object will complain."""
    with self.assertRaisesRegex(TypeError, 'Invalid PluginAPI object'):
      plugin_loader.PluginLoader('plugin_id', plugin_api=True)

  def testGetSuperclass(self):
    """Tests that GetSuperclass returns correctly."""
    self.assertEqual(
        plugin_loader.PluginLoader._GetSuperclass(plugin_base.BufferPlugin),
        plugin_base.BufferPlugin)
    self.assertEqual(
        plugin_loader.PluginLoader._GetSuperclass(plugin_base.InputPlugin),
        plugin_base.InputPlugin)
    self.assertEqual(
        plugin_loader.PluginLoader._GetSuperclass(plugin_base.OutputPlugin),
        plugin_base.OutputPlugin)
    self.assertEqual(
        plugin_loader.PluginLoader._GetSuperclass(bool),
        None)
    # Should only accept classes, not objects.
    with self.assertRaises(TypeError):
      plugin_loader.PluginLoader._GetSuperclass(self)

  def testPrePostGetSuperclass(self):
    """Tests that self.superclass gets set correctly after Create()."""
    pname = self._createPluginFile(
        '''\
        from cros.factory.instalog import plugin_base
        class OutputTest(plugin_base.OutputPlugin):
          pass
        ''')
    pl = plugin_loader.PluginLoader(pname, pname, _plugin_prefix='')
    self.assertEqual(None, pl.GetSuperclass())
    pl.Create()
    self.assertEqual(plugin_base.OutputPlugin, pl.GetSuperclass())

  def testLoadInput(self):
    """Tests getting an instance of an InputPlugin from a module."""
    pname = self._createPluginFile(
        '''\
        from cros.factory.instalog import plugin_base
        class InputTest(plugin_base.InputPlugin):
          pass
        ''')

    # Should succeed with correct superclass=InputPlugin.
    pl = plugin_loader.PluginLoader(pname, pname, plugin_base.InputPlugin,
                                    {}, plugin_api=None, _plugin_prefix='')
    plugin = pl.Create()
    self.assertIsInstance(plugin, plugin_base.InputPlugin)
    self.assertNotIsInstance(plugin, plugin_base.OutputPlugin)

    # Should fail with incorrect superclass=OutputPlugin.
    pl = plugin_loader.PluginLoader(pname, pname, plugin_base.OutputPlugin,
                                    {}, plugin_api=None, _plugin_prefix='')
    with self.assertRaisesRegex(
        plugin_base.LoadPluginError, r'contains 0 plugin classes'):
      pl.Create()

  def testLoadOutput(self):
    """Tests getting an instance of an OutputPlugin from a module."""
    pname = self._createPluginFile(
        '''\
        from cros.factory.instalog import plugin_base
        class OutputTest(plugin_base.OutputPlugin):
          pass
        ''')
    # Should succeed with correct superclass=OutputPlugin.
    pl = plugin_loader.PluginLoader(pname, pname, plugin_base.OutputPlugin,
                                    {}, plugin_api=None, _plugin_prefix='')
    plugin = pl.Create()
    self.assertIsInstance(plugin, plugin_base.InputPlugin)
    self.assertIsInstance(plugin, plugin_base.OutputPlugin)

    # Should fail with incorrect superclass=InputPlugin.
    pl = plugin_loader.PluginLoader(pname, pname, plugin_base.InputPlugin,
                                    {}, plugin_api=None, _plugin_prefix='')
    with self.assertRaisesRegex(
        plugin_base.LoadPluginError, r'contains 0 plugin classes'):
      pl.Create()

  def testSyntaxError(self):
    """Tests loading a plugin with a syntax error."""
    pname = self._createPluginFile('/')
    pl = plugin_loader.PluginLoader(pname, pname, _plugin_prefix='')
    with self.assertRaisesRegex(
        plugin_base.LoadPluginError, r'SyntaxError: invalid syntax'):
      pl.Create()

  def testRuntimeInitArgsError(self):
    """Tests loading a plugin with a runtime error: __init__ args."""
    pname = self._createPluginFile(
        '''\
        from cros.factory.instalog import plugin_base
        class InputTest(plugin_base.InputPlugin):
          def __init__(self):
            pass
        ''')
    pl = plugin_loader.PluginLoader(pname, pname, _plugin_prefix='')
    with self.assertRaisesRegex(
        plugin_base.LoadPluginError, r'TypeError: __init__\(\) takes'):
      pl.Create()

  def testRuntimeInitMethodError(self):
    """Tests loading a plugin with a runtime error: within __init__."""
    pname = self._createPluginFile(
        '''\
        from cros.factory.instalog import plugin_base
        class InputTest(plugin_base.InputPlugin):
          def __init__(self, *args, **kwargs):
            1 / 0
        ''')
    pl = plugin_loader.PluginLoader(pname, pname, _plugin_prefix='')
    with self.assertRaisesRegex(
        plugin_base.LoadPluginError,
        r'ZeroDivisionError: division by zero'):
      pl.Create()

  def testArgsInvalidError(self):
    """Tests providing invalid arguments to a plugin."""
    pname = self._createPluginFile(
        '''\
        from cros.factory.instalog import plugin_base
        from cros.factory.instalog.utils.arg_utils import Arg
        class InputTest(plugin_base.InputPlugin):
          ARGS = [
            Arg('explode', bool, 'True if device is expected to explode'),
          ]
        ''')
    # Invalid, since `explode` is a required argument.
    pl = plugin_loader.PluginLoader(pname, _plugin_prefix='')
    with self.assertRaisesRegex(
        plugin_base.LoadPluginError,
        r'Error parsing arguments: Required argument explode'):
      pl.Create()

  def testArgs(self):
    """Tests providing valid arguments to a plugin."""
    pname = self._createPluginFile(
        '''\
        from cros.factory.instalog import plugin_base
        from cros.factory.instalog.utils.arg_utils import Arg
        class InputTest(plugin_base.InputPlugin):
          ARGS = [
            Arg('explode', bool, 'True if device is expected to explode'),
          ]
        ''')
    pl = plugin_loader.PluginLoader(
        pname, config={'explode': True}, _plugin_prefix='')
    self.assertIsInstance(pl.Create(), plugin_base.InputPlugin)


if __name__ == '__main__':
  log_utils.InitLogging(log_utils.GetStreamHandler(logging.INFO))
  unittest.main()
