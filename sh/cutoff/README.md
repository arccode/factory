ChromeOS Factory Cut-off scripts
================================
The scripts here are dedicated for Chrome OS Factory Software, for the process
of turning off the device for packaging. Most clamshell devices will try to
do battery cut-off in this stage (or check battery charging level). Chromeboxes
usually prefer shutdown. Routers or non-conventional devices may prefer reboot.

Quick Setup Guide
-----------------
To change cut-off options:

1. If you are changing the cut-off options for the finalization when building
   factory toolkit, copy the `cutoff.json.default` to your board overlay into
   file path `chromeos-base/factory-board/files/py/config/cutoff.json`.
   Change values in the config file, and rebuild a new factory toolkit.
   This config file also applies to reset shim.

2. If you want to set a different value for reset shim (for example to reset
   after OQC), or for finalization when the RMA shim is already created, use
   `setup/image_tool edit_toolkit_config` to modify the cut-off config stored in
   `toolkit_config` payload.

Dependency Isolation
--------------------
This folder is shared by Chrome OS Factory Toolkit (complete execution
environment with Python) and Factory Reset Shim (also known as factory_install
image, using a very limited root file system without Python) so it must not have
any dependency with other files outside this folder.

Invocation
----------

### Toolkit

Scripts here will be installed to `/usr/local/factory/sh/cutoff`. Factory
Toolkit will execute the scripts via Gooftool.

### Reset shim
(Reset shim is built by `build_image factory_install`.)
Scripts here will be installed to `/usr/share/cutoff`. The `cutoff.json` in
private overlay will also be installed to this folder.  When reset shim boots
up, if a toolkit is packed with the reset shim, the `cutoff.json` in the
**toolkit** will override `/usr/share/cutoff/cutoff.json`.  See [Quick Setup
Guide](#quick-setup-guide) for more details.

Setting cut-off options
-----------------------
As explained in previous section, the factory software may execute cut-off
scripts using different approaches that you may override execution options.

But the most easy way would be to create a per-board configuration file so it
will be shared as default value. To do that, go to `chromeos-base/factory-board`
in your board overlay and put the files in `files/py/config/cutoff.json`.

There are few options you can set:

 - `CUTOFF_METHOD`: What to do for cut-off. Available options: `shutdown`,
     `reboot`, `ectool_cutoff`, `battery_cutoff` and `ec_hibernate`.
 - `CUTOFF_AC_STATE`: Should AC be removed of not. Available options:
     `connect_ac`, `remove_ac`.
 - `CUTOFF_BATTERY_MIN_PERCENTAGE`: Minimal allowed value for battery charging
     level (in percentage). Should be 0~100.
 - `CUTOFF_BATTERY_MAX_PERCENTAGE`: Maximal allowed value for battery charging
     level (in percentage). Should be 0~100.
 - `CUTOFF_BATTERY_MIN_VOLTAGE`: Minimal allowed value for battery voltage.
 - `CUTOFF_BATTERY_MAX_VOLTAGE`: Maximal allowed value for battery voltage.
 - `SHOPFLOOR_URL`: URL to shopfloor server that we can send request to inform
     "device is cut-off and ready for packaging".
 - `TTY`: Path of terminal for output. Defaults to /run/frecon/vt0.

The options should be set in JSON format. For example:

```json
    {
      "CUTOFF_METHOD": "battery_cutoff",
      "CUTOFF_AC_STATE": "remove_ac",
      "CUTOFF_BATTERY_MIN_PERCENTAGE": 60,
      "CUTOFF_BATTERY_MAX_PERCENTAGE": 80,
      "SHOPFLOOR_URL": "http://192.168.1.1/"
    }
```
