# Goofy Plugin #

*Goofy Plugin API* allows us to enhance Goofy's functionality based on
requirement, including:

- Run a set of python code when Goofy is starting, running, or destroying.
- Add additional UI widget on Goofy Web UI.
- Add additional menu items on Goofy Web UI menu.
- Add additional RPC functions in Goofy.


## How to Create a Plugin ##

Each plugin should be a python class that implements
`cros.factory.goofy.plugins.plugin.Plugin`. The python file that implements
the plugin should only have one plugin class. The file can be located in
`py/goofy/plugins`, or in a subdirectory under it.

For example, we can have a plugin in either:
* `py/goofy/plugins/a.py`
* `py/goofy/plugins/a/b.py`
* `py/goofy/plugins/a/b/c.py`

There is no special restriction to the class name of the plugin.


### Define: *Plugin Name* ###

To help accessing a plugin, here we define the *Plugin Name* of a plugin to be
the module name after `cros.factory.goofy.plugins`, and *NOT* including the
class name.

The example names of plugins in different location are listed:
* `py/goofy/plugins/aaa.py`: `aaa`
* `py/goofy/plugins/aaa/bbb.py`: `aaa.bbb`
* `py/goofy/plugins/aaa/bbb/ccc.py`: `aaa.bbb.ccc`

All *plugin name* mentioned in this doc follows the same rule.


## Life Cycle Functions ##

A plugin can override the following life cycle functions to run additional
logic when Goofy is running.

* `OnStart`: called when the plugin is started by Goofy.
* `OnStop`: called when the plugin is stopped by Goofy.
* `OnDestroy`: called when Goofy is shutting down.

All the life cycle functions are executed in Goofy main thread, so the
the plugin must be carefully designed to prevent blocking operations.

For example, we can have a battery monitor plugin to log battery level when
Goofy is running.

    from cros.factory.goofy.plugins import plugin
    from cros.factory.utils import type_utils

    class BatteryMonitor(plugin.Plugin):

      @type_utils.Overrides
      def OnStart(self):
        self.StartMonitoring()

      @type_utils.Overrides
      def OnStop(self):
        self.StopMonitoring()


## Resource Control ##

Sometimes we don't want Goofy plugins to access some resources when a test is
running. For example, we may want to disable battery monitor plugin when we're
doing charging test.

To provide a resource control, each plugin can declare the resources it uses
by calling the constructor of the base class.

For example:

    class BatteryMonitor(plugin.Plugin):
        def __init__(self, goofy, min_charge, max_charge):
          super(BatteryMonitor, self).__init__(
              self, goofy, used_resource=[plugin.RESOURCE.POWER])
          ...

In test list, a test can ask Goofy to stop plugins using specific resources.

For example:

    {
      "pytest_name": "battery_charging",
      "exclusive_resources": ["POWER"],
      "args": {...}
    }

Before the test starts, Goofy calls `OnStop` of `BatteryMonitor`. And `OnStart`
will be called again after the test finishes.


## RPC Function ##

A plugin can also register RPC functions in Goofy server for other plugins or
tests to control it. To register a RPC function, mark the function with
decorator `RPCFunction` in the plugin class.

The function would be registered under URL
`/plugin/plugin_name`, with `.` in the plugin name replaced by `_`

For example, we can provide log upload plugin in
`py/goofy/plugins/log_plugin/log_plugin.py`

    from cros.factory.goofy.plugins import plugin
    from cros.factory.utils import type_utils

    class GoofyLog(plugin.Plugin):

      @plugin.RPCFunction
      def FlushLog(self):
        ...

The RPC is registered in
`http://GOOFY_URL:GOOFY_PORT/plugin/log_plugin_log_plugin`

To call the function, one can use the following snippet in Python:

    from cros.factory.goofy.plugin import plugin_controller
    ...
    proxy = plugin_controller.GetPluginRPCProxy('log_plugin.log_plugin')
    proxy.FlushLog()

, or in Javascript:

    goofy.sendRpcToPlugin('log_plugin.log_plugin', 'FlushLog').then(callback)


## Menu Item ##

A plugin can add menu items in Goofy Web UI. To do this, override the function
`GetMenuItems` to return a list of menu items (`plugin.MenuItem`) objects.

For example,

    class DeviceManager(plugin.Plugin):

      @type_utils.Overrides
      def GetMenuItems(self):
        return [plugin.MenuItem(
                    text=_('View /var/log/messages'),
                    callback=self.GetVarLogMessages,
                    eng_mode_only=True),
                plugin.MenuItem(
                    text=_('View /var/log/messages before last reboot'),
                    callback=self.GetVarLogMessages,
                    eng_mode_only=True),
                plugin.MenuItem(
                    text=_('View dmesg'),
                    callback=self.GetDmesg,
                    eng_mode_only=True),
                plugin.MenuItem(
                    text=_('Device manager'),
                    callback=self.ShowDeviceManagerWindow,
                    eng_mode_only=True)]

For more details, see doc in [plugin.py](plugin.py).


## Frontend UI ##


### Provide Static Files ###

A plugin can provide its own UI static files. To provide static files,
plugin should have its own subdirectory, and put all the static files under
`<plugin_dir>/static`.

Once loaded, Goofy server maps URL `/plugin/<plugin_name>` to
`<plugin_dir>/static`, with `.` replaced by `_` in plugin name.


### Show Plugin UI ###

The plugin UI is shown as an `<iframe>` at the bottom-left corner of the
Goofy Web UI.  To provide frontend UI, simply return `True` in function
`GetUILocation`.  For example,

    class MyPlugin(plugin.Plugin):

      @type_utils.Overrides
      def GetUILocation(self):
        return True

Goofy would link the `<iframe>` to URL
`/plugin/<plugin_name>/<plugin_python_name>.html` as the entry point.

The UI location can be changed by returning one of `'testlist'`, `'console'`,
`'goofy-full'`.  Returning `True` has same effect as `'testlist'`.

Plugin can have its own Javascript file. During the plugin `<iframe>` creation,
the namespace `cros` and `goog` is set by Goofy. Therefore, plugin Javascript
can also access a set of useful tools defined in `cros` and `goog`. A `plugin`
object that provides a set of useful functions are also injected.

See [py/goofy/plugins/status\_monitor/](status_monitor) for detail example.


## Use a Plugin ##

To use a plugin, write a JSON configuration with following rule:

    {
        "inherit": "..."
        "plugins": {
          "plugin_name_a": {
            "args": {...}
          },
          "plugin_name_b": {
            "args": {...}
          },
        }
    }

Put the file under `py/goofy/plugins` or runtime configuration directory, and
indicate the configuration to be used in your test list python file by

    options.plugin_config_name = 'xxx'

The keyword `inherit` can be used to inherit several plugin configuration files.
