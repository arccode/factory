# How To Write a ChromeOS Factory Test List (In JSON)
The new test lists will be written in JSON format, and will be loaded by
`cros.factory.test.test_lists.manager`.

A test list file is a JSON file contains one object, the object can have
following fields:
* `inherit`: a list of strings, e.g. `["a.test_list", "b.test_list"]`.
    Specifies base config files for this config file, e.g. `a.test_list.json`
    and `b.test_list.json`.  Fields `constants`, `options`, `definitions` will
    be loaded and merged with current config files.  Inheritance order is
    resolved by [C3 linearization](https://en.wikipedia.org/wiki/C3_linearization).
* `constants`: key value pairs to define some constants that could be used
    later.  Please refer to [Evaluation](#Expression-Evaluation) section for
    usage of constants.
* `options`: test list options, please refer to
    `cros.factory.test.test_lists.test_list.Options`.
* `definitions`: define some reusable [test objects](#Test-Objects).
* `tests`: a list of [test objects](#Test-Objects), which are the top level
    tests in this test list.
* `__comment`: just a comment, test list manager will ignore this field.
* `override_args`: a dictionary where keys are test path you want to override
    test arguments, values are the test arguments that will be merged with old
    one.

## Examples
You can find examples under `./manager_unittest/` folder,
e.g. [a.test_list.json](./manager_unittest/a.test_list.json).

## Test Objects
Each test object represents a `cros.factory.test.factory.FactoryTest` object
(with some additional information).  Here are some attributes you can set to a
test object.

### ID
Each test item must have an ID, ID will be used to define the **path** of a
test.  **path** is defined as:

`test.path = test.parent.path + '.' + test.ID`

For example, the test group `SMT` will have test path `SMT`, and the test item
`ProbeCamera` will have test path `SMT.ProbeComponents.ProbeCamera`.

`ID` can be auto generated, see [Syntactic Sugar](#Syntactic-Sugar) for more
details.

### label
`label` is a string that will be shown on UI. `label` will be treated as an i18n
string by default.

### pytest_name and args
Leaf nodes (the test objects have no subtests) of test list should be a
**pytest**.  A pytest is a test written in python and placed under
`py/test/pytests/` in public or private factory source tree.

Each pytest can define their arguments, the `ARGS` variable in the class.  And
the `args` is used to assign values to these arguments.  `args` is a dictionary
of key value pairs where keys are mapped to the name of each arguments in
`ARGS`.

### Subtests
To create a group of tests, you just need to

```json
  {
    "label": "Test Group Label",
    "subtests": [
      "a",
      "b",
      "c"
    ]
  }
```

By default, the test group will be tested in a **sequence**, that is, if any of
subtest will be retested, **all** of subtests will be retestsed in order.  To
create a group that subtests can be run individually, **inherit** from
`TestGroup`:

```json
  {
    "label": "Test Group Label",
    "inherit": "TestGroup",
    "subtests": [
      "a",
      "b",
      "c"
    ]
  }
```

### Locals
Each test object can have a `locals` attribute, which is a dictionary
of key value pairs.  `locals` will be available when Goofy is resolving `args`
that will be passed to pytest.

### Allow Unexpected Reboots
Set `allow_reboot` to `true` if you want to allow unexpected shutdown or reboot
when running the test.

More specifically, when goofy starts up, it checks if the last running test is
marked as `allow_reboot` or not. If it's `false`, it means an unexpected
shutdown just happened, so it stops all pending tests and waits for further
manual inspection. If it's `true`, it means the shutdown is allowed. The test
will be marked as `UNTESTED`, and re-run this test if `auto_run_on_start`
is set to `true` on the test list.

Please use this option with care. The rule of thumb is to properly shutdown the
DUT whenever possible, by using the shutdown test. One usage of this option is
at SMT line, when display is not attached to the mlb, and the operator might
move the mlb to different test stations to perform the test multiple times.

### Parallel Tests
To make two or more tests run in the same time, you need to group them under a
test group, and add attribute `"parallel": true` to this test group.

### Action On Failure
The `action_on_failure` attribute allows you to decide what the next test should
be when this test fails.  There are three possible values:
* `NEXT`: this is the default value, the test list will continue on next test
    item.
* `PARENT`: stop running other tests under current parent, let parent to decide
    what the next test should be.
* `STOP`: stop running other tests.

### Teardown
Sometimes, you want a test be run after some tests are finished, no matter
those tests success or not.  For example, a test item that uploads log files to
shopfloor server should always be run despite the status of previous tests.

```json
  {
    "label": "Test Group Label",
    "subtests": [
      {
        "normal tests...",
        {
          "label": "Tear Down Group",
          "teardown": true,
          "subtests": [
            ...
          ]
        }
      }
    ]
  }
```

Tests in teardowns can have their subtests as well.  Those tests will become
teardown tests as well.  We assume that teardowns will never fail, if a teardown
test fails, Goofy will ignore the failure, and continue on next teardown test.
Therefore, for teardown tests, `action_on_failure` will always be set to `NEXT`.

### Additional Fields
Test list manager will process these fields, they are not directly used by
`FactoryTest`.

1. `inherit`: a string, the name of the base test object, default to
   `FactoryTest`.  The base test object should be defined in `definitions`
   section.  For example, you can define a `LEDTest` test object in
   `definitions` section:

   ```
   {
     "definitions": {
       "LEDTest": {
         "pytest_name": "led",
         "args" : {
           "colors": ["RED", "GREEN"]
         }
       }
     }
   }
   ```

   Now you can use "LEDTest" as base test object:

   ```
   {
     "tests": [
       {
         "id": "MyFirstLEDTest",
         "inherit": "LEDTest"
       }
     ]
   }
   ```

   If a test object defined in `definitions` section inherits itself, it means
   that it's a class defined in `cros.factory.test.test_lists.test_object`
   module.  For example, the definition of `FactoryTest` is:

   ```
   {
     "definitions": {
       "FactoryTest": {
         "inherit": "FactoryTest"
       }
     }
   }
   ```

   Please refer to [base test list](./base.test_list.json) for more examples.

2. `locals`: in JSON style pytest, attribute `locals` of a test object will be
   passed to its subtests.  And `locals` will be evaluated before set to
   `FactoryTest` object.  See `locals.test_list.json` as an example.
3. `child_action_on_failure`: default value of `action_on_failure` of subtests.
4. `__comment`: this field will be ignored and discarded by test list manager,
   it's just a comment.
5. `override_args`: another way to override arguments of a test specified by its
   path.  See `override_args.test_list.json` as an example.

## Expression Evaluation
For `args` of test object, if a value is a string and starts with `"eval! "`,
the rest of the string will be interpreted as a python expression.  The
expression will be evaluated by python `eval` statement.  However, for
simplicity, the expression has the following restrictions:

1. Single expression (not necessary single line, but the parsed result is a
   single expression)
2. Not all operators are allowed, currently, the following expressions are not
   allowed:

   1. Generator  (e.g. `(x * x for x in range(10))`)
   2. Lambda function (e.g. `lambda x: x * x`)
   3. Other expressions that don't make sense without a context, e.g. `yield`,
      `return`

3. When executing, the namespace will only contains:

   1. built-in functions
   2. `constants` and `options`
   3. `dut`, `station`
   4. `locals`
   5. `state_proxy`  (created by `state.GetInstance()`)
   6. `device`  (a short cut for `state_proxy.data_shelf.device`)

The result of evaluated expression will not be evaluated again even if it starts
with `"eval! "` as well.

## i18n support
You can use `"i18n! English string"` to specify an i18n string.
Or, an alternative way to create i18n string is:
`{"en-US": "English string", "zh-CN": "Chinese string"}`.
Therefore, both `definitions.Start.label` and `definitions.Start.args.prompt`
are valid i18n strings.

```
{
  "definitions": {
    "Start": {
      "pytest_name": "start",
      "label": "i18n! Start",
      "args": {
        "prompt": {"en-US": "English prompt", "zh-CN": "Chinese prompt"}
      }
    }
  }
}
```

## Syntactic Sugar
For simplicity, we provide the following syntactic sugar:

### Label
1. We support auto generated label from `pytest_name`.  For example, if pytest
   name is `some_test`, then the label will be `i18n! Some Test` by default.

2. Since label should always be i18n string, so `"label": "Start"` is equivalent
   to `"label": "i18n! Start"`.

### Automatic ID
1. If a test object defined in `definitions` (before merged with base test
   object) does not contain `id` field, the key string will be the default ID,
   for example:

   ```
   {
     "definitions": {
       "LEDTest": {
         "pytest_name": "led",
         "args" : {
           "colors": ["RED", "GREEN"]
         }
       }
     }
   }
   ```

   The test object `LEDTest` will have default `"id": "LEDTest"`.

   If a test object defined in `tests` does not specify `id` field, it will
   inherit from its parent, therefore, in the following snippet,

   ```
   {
     "tests": [
       {
         "inherit": "LEDTest"
       },
       {
         "inherit": "LEDTest"
       }
     ]
   }
   ```

   The first led test will be: `LEDTest`, the second one will be: `LEDTest_2`
   (`_2` is automatically appended to resolve path duplication).

2. If the test object contains only `inherit` field, you can just write a
   string, so the previous example can be simplified to:

   ```
   {
     "tests": [
         "LEDTest",
         "LEDTest"
     ]
   }
   ```

## Generic Test Lists
[generic_main.test_list.json](./generic_main.test_list.json) is an example.
And you should reuse `generic_*.test_list.json` to create a test list for your
board.

### `generic_common.test_list.json`
This defines all kinds of tests that might be used in Chromebook factory.  By
inheriting this test list, you can use most pytests directly.

### `generic_<station>.test_list.json`
We have defined `GRT`, `FAT`, `RUN_IN`, `FFT`, `SMT` stations.  All of them are
based on `generic_common.test_list.json`, with some additional station specific
tests, or test arguments overriding.

### Create Your Own Test List
Try to reuse generic test lists if possible.  In general, you need to define the
following files in private overlay:

1. `common.test_list.json`: this inherits `generic_common.test_list.json`,
   overrides some test argument, add some board specific pytests.
2. `<station>.test_list.json`: each of them inherits corresponding
   `generic_<station>.test_list.json` and `common.test_list.json`.
3. `main.test_list.json`: this inherits `<station>.test_list.json` and
   `common.test_list.json` (and `generic_main.test_list.json` if you want to
   inherit `options` and `constants`).  Defines `override_args`, `constants`,
   `options` in this file, and also the `tests`.

In most of the case, if you are not adding / removing / reordering any tests,
you only need to override `constants`, `options` and `override_args`.

### Dump Python Test List in JSON Format
On machine, you can use `factory dump-test-list <test list id> --format json` to
dump a test list in JSON format.

## Main Wipe Test Lists
This is a special test list which only runs ModelSKU, update fingerprint
firmware and finalization. The test list could be useful if you would like
to test different versions of recovery image on a finalized DUT. A typical
use case could be:
1. There's a finalized DUT, and it is booted from a recovery image. You have
   done some testing on this recovery image and would like to test another
   version of the recovery image.
2. You have a factory shim and would like to install different versions of
   recovery image from dome.
3. Upload recovery image, test image and toolkit to dome.
4. Enter recovery mode and boot into factory shim.
5. Press E to perform RSU to remove HWWP. The DUT will reboot after RSU unlock.
6. Enter recovery mode again, and press I to install from dome.
7. After installation, the DUT will reboot, and you'll see the Goofy web page.
8. Run main_wipe test list.
9. Go to step 1 and repeat the whole process.

IMPORTANT: Please **complete the finalization step**. If the pre-condition is
not met, then you can not ship the device because it violates
[factory requirements](https://chromeos.google.com/partner/dlm/docs/factory/factoryrequirements.html).

### Modify the test list accordingly
By default, the main_wipe test list inherits from generic_fat and generic_grt
test lists. You should modify the inherited test list accordingly. For example,
inherit from common test list. Moreover, you should also modify the name of
this test list to main_<model>.test_list.json. So that the DUT will
execute this test list automatically after booting into test image.

### Why does the test list run `ModelSKU` and `Fingerprint Test Group`?
Finalization will reinitialize FPMCU entropy and this will cause some problem.
(see b/194449380 for more info). Therefore, we need to first run ModelSKU to
get the device data, then reflash the FPFW, and finally, run finalization. If
the DUT you're using does not have fingerprint sensor, then you can remove
ModelSKU and fingerprint test group from the test list.
