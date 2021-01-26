# Ghost configuration on Goofy

Ghost is the client of [Overlord](../../go/src/overlord/README.md), and is
[started](../../init/goofy.d/device/ghost.sh) automatically when goofy service
starts.

The script [goofy_ghost.py](./goofy_ghost.py) is responsible of starting a
ghost client with proper configurations for Goofy.

The script does the following things:
* Read the properties file using the [standard config hierarchy for ChromeOS
  Factory](http://go/cros-factory-config).
* Set TLS certificate if found.

## Ghost properties file
The properties file use the standard config hierarchy for ChromeOS Factory.
This means that there are three levels of config:
* `/usr/local/factory/py/tools/goofy_ghost/goofy_ghost.json`: The default config
  for DUT, we'll put general items in this file.
* `/usr/local/factory/py/config/goofy_ghost.json`: Board specific config. ODM
  can put their customization in this config to override the previous one.
* `/var/factory/config/goofy_ghost.json`: Device specific config. This is only
  used by station now.

The latter config would be merged to the former one, with latter config taking
priority.

After changing any config above, to have it take effect, run `goofy_ghost
reset`.

The format of the properties file is described in [a later
section](#Format-of-ghost-properties-file).

For development: If we need to modify the properties file temporarily for
testing, we can modify the runtime config at `/run/factory/goofy_ghost.json`.
After modifying that config, run `ghost --reset`. (Don't run `goofy_ghost
reset`, it'll re-generate the runtime config again.)

## Set TLS certificate for Overlord server
If the Overlord server is configured with TLS enabled, the server certificate
would need to be passed to ghost client.

Put the certificate at `/var/factory/overlord.pem`, and it would be passed to
ghost on startup. You may need to reboot the system for this to take effect.

If the overlord server is run using cros_docker.sh, then the certificate can be
found in `cert.pem` at the same directory of cros_docker.sh after
`cros_docker.sh overlord setup`, or in `/cros_docker/overlord/cert.pem`.

## Format of ghost properties file
The ghost properties file can be any JSON object, which would be passed to
overlord server and shown on `ovl ls -v`.

The Overlord web interface expects several special keys from ghost properties
to change the display of a client: `context, ui, camera`, so goofy_ghost
validates [JSON schema](./goofy_ghost.schema.json) on these three fields.

An example of ghost properties file and explanation of each keys is as below.

Some keys that are not used by overlord itself, but by the update_ui_status
script are marked by `(update_ui_status)`.

Note that the following example isn't a valid JSON since we use comments and
long strings are broke into multiple lines for clarity. See
[goofy_ghost.sample.json](./goofy_ghost.sample.json) for
the same example with all comment removed and multiline string joined.

```javascript
{
  // Control which pages the client would be shown.
  // Available values are "ui" and "cam".
  // If "ui" is present, then a "UI" button would appear, and the client would
  // be shown in the fixture app.
  // If "cam" is present, then a "CAM" button would appear.
  "context": ["ui", "cam"],

  // Settings of the FixtureWidget.
  // The FixtureWidget is shown on the fixture app, and on dashboard when the
  // "UI" button is clicked.
  "ui": {
    // Specify which group the client would be shown in the filter in the upper
    // left corner of fixture app.
    "group": "Project X",

    // The main command that would be run once when the widget is started, and
    // the output of the command would be shown in the widget. The default value
    // is "update_ui_status".
    //
    // Special patterns in the output of the command can be used to alter the
    // display of other sections:
    // "DATA[id]='value'": Change the value of a variable in the display
    //   section.
    // "LIGHT[id]='value'": Change the status of a light in the lights section,
    //   value can be either light-toggle-on or light-toggle-off.
    "update_ui_command": "update_ui_status",

    // Settings of the display section.
    "display": {
      // A jsrender template for the content of the display section.
      // We use array of strings here for better reading.
      "template": [
        "<b>Device Info</b>",
        "<ul>",
          "<li>Version: {{:version}}</li>",
          "<li>Battery %: {{:battery_percent}}</li>",
        "</ul>"
      ],

      // Variables that are used in the template. The value of the variable is
      // initialized to "", and controlled by the output of update_ui_command.
      "data": [{
        // id should be the same as the name used in the template.
        "id": "version",

        // (update_ui_status) The initial command to run when started.
        // Output would be redirected to update_ui_status.
        "init_cmd":
          "echo DATA[version]=\\'$(cat /etc/lsb-release | \
                                   sed -n 's/^CHROMEOS_RELEASE_VERSION=//p')\\'"
      }, {
        "id": "battery_percent",

        "poll": {
          // (update_ui_status) The command to run repeatedly on fixed interval.
          // Output would be redirected to update_ui_status.
          "cmd": "echo DATA[battery_percent]= \
                    \\'$(ectool chargestate show | \
                         sed -n 's/^batt_state_of_charge = //p')\\'",

          // (update_ui_status): The interval in ms.
          "interval": 2000
        }
      }]
    },

    // Settings of the light section.
    // Each light have two states: light-toggle-on or light-toggle-off.
    "lights": [{
      // The id of the light.
      "id": "toggle",

      // The label shown on the light.
      "label_on": "shown when light is on",
      "label_off": "shown when light is off, this is optional.",

      // The initial state of the light.
      "light": "light-toggle-off",

      // Optional. The command to be run when the light is clicked.
      // Output would be redirected to the same section as update_ui_command
      // output.
      //
      // The example is a simple light that can be toggled when clicked.
      // Note that the output needs to be in a single write for the special
      // pattern to work, so it's wrapped in a "echo $()".
      "command":
        "echo $( \
           echo -n LIGHT[toggle]=\\'light-toggle-; \
           [ -f /tmp/t ] && (echo -n off; rm /tmp/t) \
             || (echo -n on; touch /tmp/t); \
           echo \\')",

      // (update_ui_status) The initial command to run when started.
      // Output would be redirected to update_ui_status.
      "init_cmd":
        "echo $( \
           echo -n LIGHT[toggle]=\\'light-toggle-; \
           [ -f /tmp/t ] && echo -n on || echo -n off; \
           echo \\')"
    }, {
      "id": "ac_present",
      "label": "AC_PRESENT",
      "light": "light-toggle-off",

      "poll": {
        // (update_ui_status) The command to run repeatedly on fixed interval.
        // Output would be redirected to update_ui_status.
        "cmd":
          "(ectool battery | grep -qw AC_PRESENT) \
             && echo LIGHT[ac_present]=\\'light-toggle-on\\' \
             || echo LIGHT[ac_present]=\\'light-toggle-off\\'",

        // (update_ui_status): The interval in ms.
        "interval": 1000
      }
    }],

    // Settings of the terminal section.
    // Each terminal is a button that can be used to open a terminal window.
    "terminals": [{
      // The name on the button. Default behavior is open a terminal of DUT.
      "name": "MAIN"
    }, {
      "name": "SERVO",

      // Optional. The output of the command would be used as the path of the
      // tty device the terminal window connect to.
      "path_cmd": "dut-control cpu_uart_pty | cut -d : -f 2"
    }, {
      "name": "SERVO_EC",
      "path_cmd": "dut-control ec_uart_pty | cut -d : -f 2"
    }],

    // Settings of the control section.
    // Each control is a button that can be used to control the DUT.
    "controls": [{
      // The name on the button.
      "name": "Factory Restart",

      // The command to be executed when the button is clicked.
      "command": "factory_restart"
    }, {
      "name": "Set LED",

      // The type of the control, "toggle" control can be in either on or off
      // state, and would execute different command when in different state.
      // Default state is off.
      "type": "toggle",

      // The command to be executed when state changed from off to on.
      "on_command": "ectool led left white",

      // The command to be executed when state changed from on to off.
      "off_command": "ectool led left auto"
    }, {
      "name": "Upgrade Toolkit",

      // "upload" control can be used to upload a file to DUT.
      // A file selector dialog would pop up when clicked to choose the file to
      // be uploaded.
      "type": "upload",

      // The destination path on DUT that the file should be uploaded to.
      "dest": "/tmp/install_factory_toolkit.run",

      // Optional. The command to be run after the file upload is complete.
      "command":
        "rm -rf /usr/local/factory && \
         sh /tmp/install_factory_toolkit.run -- -y && \
         factory_restart"
    }, {
      "name": "Download Log",

      // "download" control can be used to download a file from DUT.
      "type": "download",

      // Optional. The command to be executed before the download starts.
      "command": "dmesg > /tmp/dmesg.log",

      // The name of the file to be downloaded.
      "filename": "/tmp/dmesg.log"

      // "filename_cmd" can also be specified instead of "filename", to specify
      // a command to be run to retrieve the file name.
      // "filename_cmd": "echo /tmp/dmesg.log"
    }, {
      "name": "Properties",

      // "link" control can be used to link to another page.
      "type": "link",

      // URL template of the target. Supported attributes are:
      //   host: the hostname of the webserver serving this page.
      //   port: the HTTP port of the webserver serving this page.
      //   client: the client object.
      "url": "/api/agent/properties/{{:client.mid}}"
    }, {
      "name": "LED Control",

      // "group" control can be used for a group of related controls.
      // Currently each sub-control in the group should be a simple control.
      // (type is not well supported.)
      "group": [{
        "name": "WHITE",
        "command": "ectool led left white"
      }, {
        "name": "AMBER",
        "command": "ectool led left amber"
      }, {
        "name": "OFF",
        "command": "ectool led left off"
      }, {
        "name": "AUTO",
        "command": "ectool led left auto"
      }]
    }],

    // Files that would be streamed (tail -f) and output to the auxiliary log
    // section.
    "logs": ["/var/log/factory.log"]
  },

  // Setting of the camera window.
  "camera": {
    // The command for camera streaming, see stream_camera.py for format detail.
    "command": "/usr/local/factory/py/tools/stream_camera.py --size 640x480",
    "width": 640,
    "height": 480
  }
}
```
