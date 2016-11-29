# How To Write a ChromeOS Factory Test List
Test lists are defined by **python files** under this
( `platform/factory/py/test/test_lists` ) directory.  Each of these files
should have a module level `CreateTestLists` function, this function will be
called
when Goofy starts.  Here is an example of a test list file:

```python
import factory_common  # pylint: disable=unused-import
from cros.factory.test.test_lists import test_lists


def CreateTestLists():
  # create a test list with ID 'main'
  with test_lists.TestList(id='main') as test_list:
    # setup test list options
    test_list.options.xxx = ...
    # you can also put them into a function, e.g. SetOptions
    SetOptions(test_list.options)

    with test_lists.FactoryTest(
        id='SMT',
        label_en='SMT Tests',
        label_zh=u'SMT 测试',
        action_on_failure='STOP'):
      with test_lists.FactoryTest(
          id='ProbeComponents',
          label_en='Probe Components',
          label_zh=u'侦测元件',
          parallel=True):
        test_lists.FactoryTest(
            id='ProbeAccelerometer',
            label_en='Probe Accelerometer',
            label_zh=u'侦测加速度计',
            pytest_name='i2c_probe',
            dargs={
                'bus': 1,
                'addr': 0x30,
            })
        test_lists.FactoryTest(
            id='ProbeCamera',
            label_en='Probe Camera',
            label_zh=u'侦测相机',
            pytest_name='i2c_probe',
            dargs={
                'bus': 1,
                'addr': 0x45,
            })
      test_lists.RebootStep(id='Reboot')
      test_lists.FactoryTest(
          id='LED',
          label_en='LED Test',
          label_zh=u'LED 测试',
          pytest_name='led',
          action_on_failure='PARENT',
          has_ui=True,
          dargs={
              'colors': ['RED', 'BLUE', 'GREEN']
          })
      test_lists.ShutdownStep(id='Shutdown')

    with test_lists.FactoryTest(
        id='RunIn',
        label_en='RunIn Tests',
        label_zh=u'RunIn 測試',
        action_on_failure='STOP'):
      test_lists.FactoryTest(
          id='StressAppTest',
          label_en='StressAppTest'
          label_zh=u'压力测试',
          pytest_name='stressapptest',
          dargs=dict(seconds=30 * 60,
                     memory_ratio=0.75,
                     free_memory_only=True,
                     wait_secs=5,
                     disk_thread=True))
```

This will create a test list named `main`, with the following structure:

```text
main
 |-- SMT
 |    |-- ProbeComponents
 |    |    |-- ProbeAccelerometer
 |    |    `-- ProbeCamera
 |    |
 |    |-- Reboot
 |    |-- LED
 |    `-- Shutdown
 |
 `-- RunIn
      `-- StressAppTest
```

Where:
* `ProbeAccelerometer` and `ProbeCamera` will be run in **parallel**.
* the device will be rebooted on `Reboot` test.
* the user interface of `LED` (if any) will be shown when running.
* the device will be shutdown on `Shutdown` test.
* If any of the tests under `SMT` fails, Goofy will stop testing, `RunIn` won't
    be run.
* StressAppTest will be run for 30 minutes.

Detail explanation of each attributes are available in the following sections.

## ID
Each test item must have an ID, ID will be used to define the **path** of a
test.  **path** is defined as:

`test.path = test.parent.path + '.' + test.ID`

For example, the test group `SMT` will have test path `SMT`, and the test item
`ProbeCamera` will have test path `SMT.ProbeComponents.ProbeCamera`.

**Each test path must be unique in a test list.**  That is, you can have several
test with ID `Shutdown`, but they have to have different test path.

## label_en and label_zh
Label is a string that will be shown on UI.  Remember to use `u'中文'` for
Chinese.

## pytest_name and dargs
Leaf nodes (the test items have no subtests) of test list should be a
**pytest**.  A pytest is a test written in python and place under
`py/test/pytests/` in public or private factory source tree.

Each pytest can define their arguments, the `ARGS` variable in the class.  And
the `dargs` is used to assign values to these arguments.  As you can see on the
sample code above, `dargs` is a dictionary of key value pairs where keys are
mapped to the name of each arguments in `ARGS`.

## Subtests
To create a group of tests, you just need to

```python
  with test_lists.FactoryTest(id='TestGroupID'):
    # add subtests here
    ...
```

## has_ui
Set `has_ui=True` if this test needs to interact with operator, e.g. showing
informations or getting user input.

## never_fails
Set `never_fails=True` if you don't want this test to fail in any case.
The test will still be run, but when it fails, it will not be marked as failed.

## Parallel Tests
To make two or more tests run in the same time, you need to group them under a
`FactoryTest`, and add attribute `parallel=True` to this FactoryTest.
You can see `ProbeComponents` in above as an example.

## Action On Failure
The `action_on_failure` attribute allows you to decide what the next test should
be when this test fails.  There are three possible values:
* `NEXT`: this is the default value, the test list will continue on next test
    item.
* `PARENT`: stop running other tests under current parent, let parent to decide
    what the next test should be.
* `STOP`: stop running other tests.
