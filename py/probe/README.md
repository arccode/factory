# ChromeOS Factory Probe Framework

[TOC]

## Introduction & Overview

This framework focuses on supplying different ways to scan the device so that
the user can easily figure out whether a specific hardware component is
installed.  In the factory flow, our factory software does a series of tests.
Some of the tests have to figure out whether a specific hardware component is
installed on the device.  One example is that we need to probe the device
to collect components infomation when the HWID string is being generated.

The idea of probing a component can be separated into 2 steps:

1. Fetch information of those kind of components.
2. Compare the fetched data with the expected value of that component.

For example, if we want to know whether a USB camera device whose vendor id is
`01bd` is installed or not. We can do:

1. Fetch information about usb devices by running the command `lsusb`.
2. Verify if there's a line of the output contains `01bd:....` substring.

To ask the probe framework to perform such task, you have to write a config
file to describe how to probe the component on DUT, and then either use the
command line interface or the program interface to run the probe framework.
In the above case for example, you will have a probe config file like:

```json
{
  "camera": {
    "usb_01bd": {
      "eval": "usb",
      "expect": {
        "idVendor": "01bd"
      }
    }
  }
}
```

And you have to run the probe framework on the DUT (let's say, you store the
above configuration in the file `/tmp/probe_config_file.json`):

```shell
root@localhost:/tmp $ probe probe --config-file /tmp/probe_config_file.json
```

The output might look like:

```json
{
  "camera": [
    {
      "name": "usb_01bd",
      "values": {
        "idVendor: "01bd",
        "idProduct: "1234",
        ...
    },
    {
      "name": "usb_01bd",
      "values": {
        "idVendor: "01bd",
        "idProduct: "2468",
        ...
    },
    ...
  ]
}
```


## Terminology Definitions

* **probe function**: A function which is available in the probe statement.  A
  probe function can probe specific kind of hardware components (for example,
  the function `usb` can probe all usb devices) or a specific kind of resource.

* **probe statement**: A statement in *json* format which describes the
  probe functions to be evaluated and the expected probed values.

* **probe config file**: A json config file which contains probe statements for
  each components the user want to probe.

* **probed results**: The corresponding output of a probe statement, must be a
  list of dictionaries.  Each dictionary contains attributes of a probed
  component, also known as **probed values**.


## Detail Usage

### The Syntax of a Probe Statement

The probe framework supplies many probe functions for different kind of
components.  However, it's the user's responsibility to tell the framework
which function to run and what's the expected result values if the hardware
component which interests the user is found.  A probe statement is a json
format dictionary that describes the task the probe framework should perform.

|||---|||
#### The Syntax of a Probe Statement

```json
{
  "eval": <functions_to_be_evaluated>,
  "keys": <a_list_of_key>,
  "expect": {
    <key1>: <value1>,
    <key2>: <value2>,
    ...
  }
  "information": <a_dict_of_any_key_values>
}
```

#### An Example of a Probe Statement

```json
{
  "eval": "usb",
  "keys": [
    "idVendor",
    "idProduct",
    "bcdDevice"
  ],
  "expect": {
    "idVendor": "1122",
    "idProduct": "3344"
  },
  "information": {
    "key_a": "value_a"
  }
}
```

|||---|||

* `<functions_to_be_evaluated>` is a little bit more complex than other parts.
  Its format can be described by following context free like grammar:

```
<functions_to_be_evaluated> := <function> | <functions>
<functions> := [<function>, <function>, ...]
<function> := "<function_name>"  # Valid if the function doesn't have any
                                 # essential arguments.
              | "<function_name>:<arguments>"  # Valid if <arguments> is a
                                               # string.
              | {<function_name>: <arguments>}
<function_name> := <string>  # Name of a function, must be implemented as a
                             # python file in functions/ directory.
<arguments> := <string>  # Valid if there is only one essential argument.
               | <a_dict_of_function_arguments>
```

Please refer to
[this document](https://storage.googleapis.com/chromeos-factory-docs/sdk/probe/index.html#functions)
for each function's spec.

* `"keys"` field is optional.  The probe framework outputs a dictionary for each
  probed component to describe the attributes of that component (like
  `idProduct`, `idVendor`, `bcdDevice` of a USB device).  This field allows
  the user to restrict the probe framework to output only some of the
  attributes.

* `"expect"` field is optional.  This field lets the probe framework output
  the result only if it matches the expected values.  The probe framework
  currently supports different matching methods such as string comparison and
  regular expression.  Please refer to
  [this document](https://storage.googleapis.com/chromeos-factory-docs/sdk/probe/functions/match.html)
  for detail.

* `"information"` field is also optional.  When the probe framework finds this
  special field, the probe framework will just add the whole field into the
  output.

### The Syntax of a Probe Config File

To ask the probe framework to probe all components the user is interested in,
the user has to write a probe config file which contains probe statements for
each components, classified by user-defined component categories.

|||---|||
#### The Syntax of a Probe Config File

```json
{
  <component_category>: {
    <component_name_1>: <probe_statement_for_component_1>,
    <component_name_2>: <probe_statement_for_component_2>,
    ...
  },
  <component_category>: {
    ...
  },
  ...
}
```

#### An Example of a Probe Config File

```json
{
  "camera": {
    "camera_usb_1122_3344": {
      "eval": "usb",
      "expect": {
        "idVendor": "1122",
        "idProduct": "3344"
      },
      "information": {
        "key_a": "value_a"
      }
    },
    "camera_pci_3344_5566": {
      "eval": "pci",
      "expect": {
        "vendor": "3344",
        "device": "5566"
      }
    }
  },
  "touchscreen": {
    "elan": {
      "eval": "touchscreen_i2c"
    }
  }
}
```
|||---|||

* `<component_category>` allows you to group some components together so that
  you can easily count the number of found components of same category.  For
  example, you can count the number of cameras installed on the device by
  grouping all probe statements for camera components together.
* `<component_name>` is just a human readable string which makes the probed
  results more human friendly.

* `<probe_statement_for_component>` is the probe statement described in the
  previous section.

### Output Format

The corresponding results of a probe statement must be a list of dictionaries.
Each dictionary is returned for one probed component (like the command `lsusb`,
the probe function might detect multiple components on the DUT).  A dictionary
contains probed values of the component.  For example, the probe statement:

```json
{
  "eval": "usb",
  "expect": {
    "idVendor": "!re ^012.$"
  }
}
```

might have corresponding probed results like:

```json
[
  {
    "idVendor": "0123",
    "idProduct": "aaaa",
    ...
  },
  {
    "idVendor": "0124",
    "idProduct": "bbbb",
    ...
  },
  {
    "idVendor": "0125",
    "idProduct": "cccc",
    ...
  }
]
```

However, the format of the output of the probe framework is a little different
than just concatenating all probed results of each probe statement.  The probe
framework will classify the probed results by the categories specified in
the config file.  The output of the probe framework is also in json format:

|||---|||
#### The Output Format of the Probe Framework

```json
{
  <component_category>: [
    {
      "name": <component_name>,
      "values": <probed_values>,
      "information": <same_as_the_information_field_in_the_probe_statement>
    },
    ...
  ]
}
```

#### An Example of the Output
```json
{
  "camera": [
    {
      "name": "camera_usb_1122_3344",
      "values": {
        "idVendor": "1122",
        "idProduct": "3344",
        "bcdDevice": "1234"
      },
      "information": {
        "key_a": "value_a"
      }
    }
  },
  "touchscreen": []
}
```
|||---|||

### Program Interface

If your program has to probe the system, please call the methods defined in
`probe_utils.py`.  If your program just needs to get some information of a
specific component from the system, it's okay to just import the probe
function for that kind of component and call the method directly.

### Command Line Interface

The probe framework has a command line interface `bin/probe`.  Please run

```shell
$ probe --help
```

for detail document.


## Framework Structure

The probe framework is designed to be easily extended.  It is mainly composed
by 5 parts:

* `function.py`: Core part of the whole probe framework.  This module defines
  a base class of a function, implements ways to loading/executing functions,
  etc.

* `functions/`: All implemented functions which are available in probe
  statements are in this directory.

* `lib/`: This package contains some useful methods and unimplemented base
  classes to collect shared logic between each functions.  By doing this, we
  can prevent each function from having duplicated code for similar features
  (like caching the probe results).

* `probe_utils.py`: The main program interface of the probe framework.  This
  module exports some methods for other part of factory software to call.

* `probe_cmdline.py`: Command line interface for the developer to use the
  probe framework directly.
