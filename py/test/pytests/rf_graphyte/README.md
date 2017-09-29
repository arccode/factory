Graphyte Tests
==============
This folder contains implementation for RF chip's transmitting and
receiving capabilities using *Graphyte* framework.

## Introduction of Graphyte Framework

Graphyte is aimed to be a RF testing framework that runs at Linux and
ChromeOS, and provide a unified RF testing way for each product in
Google. It contains three parts: Graphyte framework, DUT plugin and
instrument plugin. Before running this test, please make sure all of
them are installed into the system.

## Usage example

    {
      "pytest_name": "rf_graphyte",
      "args": {
        "graphyte_config_file": "conductive_config.json",
        "server_parameter_dir": "rf_conductive",
        "enable_factory_server": true,
        "verbose": true
      }
    }

Note that the config files should be placed in this folder, including
Graphyte global config, port config, test plan, and device config.


## How to use rf_graphyte in a new project

1. Write the Graphyte DUT plugin for the new device.
   The DUT plugin is located at private overlay
   `chromeos-base/graphyte-<board>`
2. Make sure the instrument already has the plugin.
3. Try to run Graphyte framework itself.
4. Move all config files into `py/test/pytests/rf_graphyte/` folder.
5. (Optional) If you need to update the config in the factory, place
   the latest config files in shopfloor
   `shopfloor_data/parameters/<server_parameter_dir>/` folder.
