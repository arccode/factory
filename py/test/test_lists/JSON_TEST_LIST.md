# How To Write a ChromeOS Factory Test List (In JSON)
The new test lists will be written in JSON format, and will be loaded by
`cros.factory.test.test_lists.manager`.

A test list file is a JSON file contains one object, the object can have
following fields:
* `inherit`: a list of strings, e.g. `["a.test_list", "b.test_list"]`.
    Specifies base config files for this config file, e.g. `a.test_list.json`
    and `b.test_list.json`.  Fields `constants`, `options`, `definitions` will
    be loaded and merged with current config files, values defined in latter
    config file will override values defined in former one.  (Current config
    file is always the last one.)
* `constants`: key value pairs to define some constants that could be used
    later.  Please refer to [Evaluation](#Expression-Evaluation) section for
    usage of constants.
* `options`: test list options, please refer to
    `cros.factory.test.factory.Option`.
* `definitions`: define some reusable [test objects](#Test-Objects).
* `tests`: a list of [test objects](#Test-Objects), which are the top level
    tests in this test list.
* `__comment`: just a comment, test list manager will ignore this field.

## Examples
You can find examples under `./manager_unittest/` folder,
e.g. [a.test_list.json](./manager_unittest/a.test_list.json).

## Test Objects
Each test object represents a `cros.factory.test.factory.FactoryTest` object
(with some additional information).  Please refer to
[TEST_LIST.md](./TEST_LIST.md) for attributes that are inherit from FactoryTest.

### Additional Fields
These fields are only meant for new test list loader:

1. `inherit`: a string, name of the base test object, default to `FactoryTest`.
   The base test object should be defined in `definitions` section.  For
   example, you can define a `LEDTest` test object in `definitions` section:

   ```
   {
     "definitions": {
       "LEDTest": {
         "inherit": "OperatorTest",
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
   that it's a class defined in `cros.factory.test.factory` module.  For
   example, the definition of `FactoryTest` is:

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

2. `child_action_on_failure`: default value of `action_on_failure` of subtests.
3. `__comment`: this field will be ignored by test list manager, it's just a
   comment.

## Expression Evaluation
For `args` of test object, if a value is a string and starts with `"eval!"`, the
rest of the string will be interpreted as a python expression.  The expression
will be evaluated by python `exec` statement.  However, for simplicity, the
expression has the following restrictions:

1. Single expression (not necessary single line, but the parsed result is a
   single expression)
2. Not all operators are allowed, currently, the following expressions are not
   allowed:

   1. Generator  (e.g. `(x * x for x in xrange(10))`)
   2. Lambda function (e.g. `lambda x: x * x`)
   3. Other expressions that don't make sense without a context, e.g. `yield`,
      `return`

3. When executing, the namespace will only contains:

   1. built-in functions
   2. `constants` and `options`
   3. `dut`, `station`
   4. `session`

The result of evaluated expression will not be evaluated again even if it starts
with `"eval!"` as well.

## i18n support
You can use `"i18n!English string"` to specify an i18n string.
Or, an alternative way to create i18n string is:
`{"en-US": "English string", "zh-CN": "Chinese string"}`.
Therefore, both `definitions.Start.label` and `definitions.Start.args.prompt`
are valid i18n strings.

```
{
  "definitions": {
    "Start": {
      "inherit": "OperatorTest",
      "pytest_name": "start",
      "label": "i18n!Start",
      "args": {
        "prompt": {"en-US": "English prompt", "zh-CN": "Chinese prompt"}
      }
    }
  }
}
```

## Syntactic Sugar
For simplicity, we provide the following syntactic sugar:

### Automatic ID
1. If a test object defined in `definitions` (before merged with base test
   object) does not contain `id` field, the key string will be the default ID,
   for example:

   ```
   {
     "definitions": {
       "LEDTest": {
         "inherit": "OperatorTest",
         "pytest_name": "led",
         "args" : {
           "colors": ["RED", "GREEN"]
         }
       }
     }
   }
   ```

   The test object `LEDTest` will have default `id` `"LEDTest"`.

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

   The first led test will be: `LEDTest`, the second one will be: `LEDTest-2`
   (`-2` is automatically appended to resolve path duplication).

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

3. On the other hand, if a test object is defined without inheriting anything,
   then the ID will be it's `pytest_name` (or just `'TestGroup'` if it's a group
   of tests).

   ```
   {
     "tests": [
       {
         "pytest_name": "led",
         "args" : {
           "colors": ["RED", "GREEN"]
         }
       }
     ]
   }
   ```

   The test object in above example will have ID `led`.
