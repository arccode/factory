# Probe Tests

This folder contains implementation for component probing test using
the probe framework at `FACTORY_ROOT/py/probe`

## Introduction of Probe Framework

Probe framework is aimed to replace the `gooftool probe`.
The method of `gooftool probe` is "what is usually found on a laptop",
instead of "what component is in AVL". During more and more project,
we got problems like:
- The component can or cannot be probed.
- The component should be probed but it's not at the usual place.
- A value is probed but it's incorrect value.

The new probe framework provides a series of functions to probe components.
Component vendors or pytest users should assign the function and expected probed
value for the target component. Thus we can avoid adding more and more special
case for those exception cases.

## Usage Example

    FactoryTest(
        id='ProbeComponent',
        label=_('Probe Components'),
        pytest_name='probe',
        dargs={
            'config_file': 'probe_board_smt.json',
            'overridden_rules': [
                ('flash_chip', '==', 2)
            ]
        })


## Notes for Migration from Legacy Pytests

Before implementing the probe pytest, we had several probing pytest for
different kinds of components. Now we can use this pytest to replace them.

### i2c_probe

i2c_probe pytest is to probe the I2C components. Now we can use "i2c" probe
function to probe I2C component. Here is a example:

The declaration of i2c_probe pytest:

    FactoryTest(
        id='TouchpadProbe',
        pytest_name='i2c_probe',
        dargs={'bus': 8,
               'addr': [0x49, 0x50],
               'r_flag': True})

Then the config file of probe pytest should be:

    {
      "touchpad": {
        "foo_touchpad": {
          "eval": {
            "i2c": {
              "bus_number": "8",
              "addr": "0x49",
              "use_r_flag": true
            }
          },
          "expect": {}
        },
        "bar_touchpad": {
          "eval": {
            "i2c": {
              "bus_number": "8",
              "addr": "0x50",
              "use_r_flag": true
            }
          },
          "expect": {}
        }
      }
    }

Please refer `probe_sample_i2c.json` for more example.
