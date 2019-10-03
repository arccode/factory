# Chrome OS Reference Python Factory Tests

This folder contains all reference factory tests for Chrome OS Factory Software.

For more details of individual test, please look at the
[SDK document](https://storage.googleapis.com/chromeos-factory-docs/sdk/pytests/index.html)
or read the source of individual tests.

## Pytest Overview

Take [`start.py`](start.py) as an example, a pytest should contain 4 sections.
  * Copyright header
  * Test documentation
  * Imports
  * Implementation

### Copyright header

Always add copyright header to the beginning of the file.
```python
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
```

`2018` is year of file created date.

### Test Documentation

To help both developers and non-developers understand better how these tests
works, how to use it and what's needed to make it run, we have defined a
template for documentation. The tests will be processed by
[Sphinx Documentation](http://sphinx-doc.org), so you just need to write the
module doc string in
[reStructedText format](http://www.sphinx-doc.org/en/stable/rest.html) with
following sections:
```python
"""Test summary here.

Description
-----------
A section for who wants to know what this test is, and how to use it.

You probably want to write the first section as a general description, and
remaining sections to explain more details, and how to assign the arguments
if the test arguments are pretty complicated (or try using a JSON configuration
via `config_utils` instead).

Test Procedure
--------------
Write "This is an automated test without user interaction." as first line if
the test does not need user interaction.

This is a section as "reference to write SOP for operators". Use simpler words
and abstraction of what will happen.

Dependency
----------
This is a section about "what people will need when they want to port the test
for a new platform, for example Android or even Windows.

Try to list everything needed outside Chrome OS factory repo, especially
kernel and driver dependency.

If you are using Device API (`cros.factory.device.*`), try to list the explicit
API you are using, with few typical dependency that it needs.

Examples
--------
Examples of how to use this test (in test list). Usually we want a "minimal" one
explaining what default behavior it will do, with few more examples to
demonstrate how to use the arguments.
"""
```
To preview your changes to doc, run `make doc` in chroot and browse
`build/doc/pytests/index.html`.

For more examples on how to write these docs and how they looks on SDK site, try
to look at following tests:
- [update_device_data](update_device_data.py), [HTML version](https://storage.googleapis.com/chromeos-factory-docs/sdk/pytests/update_device_data.html)
- [touchpad](touchpad.py), [HTML version](https://storage.googleapis.com/chromeos-factory-docs/sdk/pytests/touchpad.html)
- [sync_factory_server](sync_factory_server.py), [HTML version](https://storage.googleapis.com/chromeos-factory-docs/sdk/pytests/sync_factory_server.html)
- [shopfloor_service](shopfloor_service.py), [HTML version](https://storage.googleapis.com/chromeos-factory-docs/sdk/pytests/shopfloor_service.html)

### Imports

Import lines are organized in 3 categories:
* Standard python libraries, e.g. `import os`
* Third-party modules, e.g. `import jsonlibrpc`
* ChromeOS Factory modules

### Implementation

All pytests are a python class inherits [`test_case.TestCase`](../test_case.py),
which is a subclass of `unittest.TestCase` from Python
[unittest](https://docs.python.org/2/library/unittest.html) module.  When a
pytest is executed, the following functions will be called (in exact order):
1. `setUp()`
2. `runTest()`
3. `tearDown()`

## Writing a new test

All the tests must have implementation file named in
`lowercase_with_underline` style and the Python class named in `CamelCase`
style, following [PEP-8](https://www.python.org/dev/peps/pep-0008/) and Chrome
OS Factory Coding Style.  You can write test as a single Python file like
[`start.py`](start.py), or implement it as Python package in its own folder like
[`probe/`](probe/).

To use your test (say `mytest.py`), define an entry in
[test list](../test_lists/README.md):
```python
  {
    "pytest_name": "mytest"
  }
```

## Using arguments

To read arguments specified from test list, use
`cros.factory.utils.arg_utils.Arg` by adding declarations as class variable. For
example:
```python
  ARGS = [Arg('wait_secs', int, 'Wait for N seconds.', default=0)]
```

Then you can use this by reading `self.args.wait_secs`.

Since JSON serialization doesn't support `tuple` type, new pytests shouldn't
use `tuple` in argument type, and should use `list` instead.

### Schema validation

If the argument is complicated, you may want to define a schema rule to
validate the structure of the schema. For example:
```python
  Arg(..., schema=schema_object)
```

The schema object should be one of the schema classes defined in
[schema.py](../../utils/schema.py). Then the argument value would
automatically be validated with the schema rule.

You can check [tablet_rotation.py](tablet_rotation.py) as an example usage.

## Using user interface

The Chrome OS Factory Software provides a web based user interface.  The test UI
object will be injected to test instance as `self.ui`.  Read
[Test UI API](https://storage.googleapis.com/chromeos-factory-docs/sdk/test_ui_api.html)
for more details.
