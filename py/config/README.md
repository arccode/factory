ChromeOS Factory Software Build Configuration
=============================================

This directory contains *Build configuration* JSON config and schema files and
will be visited by module `cros.factory.utils.config_utils`.

To add files, create the right JSON (config and schema) files in board overlay
 `factory-board/files/py/config/` and install into system.

## List of available config

### [whitelabel_reg_code.sample.json](./whitelabel_reg_code.sample.json)
This is a sample config file for enabling separate registration code for white
label projects.
While using this, ODM/OEM needs to:
- Copy the file to the project private overlay.
- Rename the file to whitelabel_reg_code.json.
- Change/Add project specific configurations in the whitelabel_reg_code.json.
ODM/OEM needs to follow below sample to config the content:
Sample content:
```
{
  "phaser360": {
    "laser": false,
    "dopefish": false
  },
  "bobba360": {
    "gik360": false
  }
}
```
Note:
1. The first level keys of `phaser360`/`bobba360` should be the model name of
your device which could be get by `#cros_config / name` in dut.
2. The second level keys of `dopefish`/`gik360` is the whitelabel-tag of the
white label device belongs to the model listed as the first level keys. The name
could be get by `#cros_config /identity whitelabel-tag` in dut.
3. The value of the second level keys are indicating whether the registration
code for the corresponding whitelabel devices are enabled or not:
  > `true`: the feature is enabled, which means ODM/OEM applied separate
registration code bundle for the device, the software will check the
registration code according to the whitelabel device name.

  > `false`: the feature is disabled, which means ODM/OEM doesn’t apply
separate registration code bundle for the device and will use the same
registration code bundle as the model it belongs to, the software will check
registration code according to the model name.
- Submit new configuration file to your private overlay code base.
- Make sure to use the registration code for your whitelabel devices in factory.
- If all steps are setup correctly, `factory.par gooftool verify_vpd` will pass.
