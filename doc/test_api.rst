Test API
========

Overview
--------
This document describes how to write new factory tests and integrate
them into the testing framework.

Basics
------
Factory tests are implemented as Python unit tests. Each factory test
is a subclass of the `unittest.TestCase
<https://docs.python.org/2/library/unittest.html#unittest.TestCase>`_
class, and may make full use of the Python ``unittest`` API (e.g., all
the ``assert`` methods, ``fail``, ``setUp``, ``tearDown``, etc.). The
factory SDK also provides APIs that can be used to parse test
arguments (see `Test arguments`_), and to interact with the test UI
running in the browser (see :ref:`test-ui-api`).

Each factory test should at minimum contain

* a ``runTest`` method
  containing the test implementation (see `Test implementation`_), and
* an ``ARGS`` attribute describing the arguments that may be used
  by the test list when invoking the test (see `Test arguments`_).

Where to put your test
----------------------
Each factory has a name (like ``bad_blocks`` or ``lcd_backlight``).
For simple tests containing only a Python file, put the test code
in

  :samp:`py/test/pytests/{name}.py`

Alternatively, if your test has accompanying files (such as HTML or
JavaScript files), you may create a directory for it and put the code
in

  :samp:`py/test/pytests/{name}/{name}.py`. [*]_

Within this file, there should be a single subclass of `unittest.TestCase`.
There can be only one test class per module, so if you need to have different
test cases, you need to separate them into different modules. But you can create
a directory for them, for example:

  - :samp:`py/test/pytests/{dir_name}/{test1}.py`
  - :samp:`py/test/pytests/{dir_name}/{test2}.py`
  - :samp:`py/test/pytests/{dir_name}/{test3}.py`.

In this case, the name of your tests are :samp:`{dir_name}.{test1}`,
:samp:`{dir_name}.{test2}` and :samp:`{dir_name}.{test3}`.

To know more about how we load a pytest from name, please refer to
:py:func:`cros.factory.test.utils.pytest_utils.LoadPytestModule`.

.. [*] Since the ``__init__.py`` of a package will be loaded whenever its
       submodule is imported. We recommand keeping ``__init__.py`` empty to
       prevent longer loading time if ``__init__.py`` is too large.

Test implementation
-------------------
Your test should contain a ``runTest`` method containing the body of
the test.  (As with all Python unittests, it may also contain a
``setUp`` and ``tearDown`` method.  ``setUp`` is run first, and
``tearDown`` is run after the test passes or fails; although note
that ``tearDown`` may not be run if the test is forcibly stopped.)

The test is considered to have succeeded if the ``runTest`` method
returns.  The test will fail if:

* your test calls any of the ``unittest.TestCase.assertXXX`` methods,
  such as `assertTrue
  <https://docs.python.org/2/library/unittest.html#unittest.TestCase.assertTrue>`_,
  and the assertion fails. For example, this will cause your test to
  fail with a good error message if a file does not exist as expected:

    self.assertTrue(
      os.path.exists(self.args.path),
      'File %r does not exist' % self.args.path)

* your test calls `self.fail
  <https://docs.python.org/2/library/unittest.html#unittest.TestCase.fail>`,
  which tells the Python unit test framework to raise an exception.

* your test directly raises an exception with ``raise``.

* code that you call directly or indirectly raises an exception. For
  example, if you call ``subprocess.check_call``, and ``check_call``
  raises a ``CalledProcessError`` that you do not catch, your test
  will fail. If you want such a failure in ``check_call`` to cause
  your test to fail, you can choose to not catch the exception and let
  it propagate out of your ``runTest`` method.

There are several key APIs you will need to understand to write your
test:

* `Test arguments`_ allow your test to handle arguments specified
  in test lists.

* :ref:`test-ui-api` allows your test to provide a UI to interact with
  the operator or show status messages.  If your test is simple and
  does not require interaction with the user, you may choose not to
  provide a UI.

Test arguments
--------------
Test lists need to customize the behavior of tests in various
situations, e.g., to specify different limits or parameters or to
enable/disable various checks. To allow this sort of customization,
you can declare test arguments in your test case by adding an ``ARGS``
attribute describing the supported set of arguments. ``ARGS`` is a
list of items of type :py:class:`cros.factory.utils.arg_utils.Arg`.

For example::

  import unittest
  from cros.factory.utils.arg_utils import Arg

  class BadBlocksTest(unittest.TestCase):
    ARGS = [
      Arg('path', str, 'The path to a temporary file to use for testing.'),
      Arg('max_bytes', int, 'Maximum size to test, in bytes.',
          default=16*1024*1024),
    ]

This declares two arguments: ``path`` is a required string, and
``max_bytes`` is an optional number defaulting to 16 megabytes.

The test list might contain an entry like::

  {
    "pytest_name": "bad_blocks",
    "args": {
      "path": "/usr/local/foo",
      "max_bytes": 8388608
    }
  }

The factory test runner will check that:

* all the arguments in the test list are valid arguments (e.g.,
  you don't accidentally specify a ``filename`` argument, since
  ``filename`` is not declared in ``ARGS``).
* all required arguments (in this case ``path``) are specified.
* all the arguments are of the correct type (e.g., you don't say
  ``max_bytes='foo'``, since ``max_bytes`` must be an ``int``).

.. py:module:: cros.factory.utils.arg_utils

.. autoclass:: Arg

   .. automethod:: __init__

Once you have declared the arguments used by your test,
you can use ``self.args`` anywhere in your test implementation
to refer to the value of that argument.  For example::

  class BadBlocksTest(unittest.TestCase)::
    ...  # see above for ARGS = [...] declaration

    def runTest(self):
      logging.info('path=%s, max_bytes=%d',
                   self.args.path, self.args.max_bytes)

.. py:module:: cros.factory.test.utils.pytest_utils

.. autofunction:: LoadPytestModule
