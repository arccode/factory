Test List API
=============

Overview
--------

The Test List API is used to create test lists.  A :index:`test list`
is a specification for the series of tests that should be run as part
of the factory test process, and in what order and under what
conditions.

Each test list is a tree of nodes.  Conceptually, each node is one of
the following:

* A container for other tests (like a folder in the filesystem).  When
  a container is run, the tests that it contains are run in sequence.
* An autotest within in the ``third_party/autotest`` repository (e.g.,
  ``hardware_SAT``, which runs the stress app test).
* A pytest, which is a test written using the standard Python unit test API.

Test lists have IDs (like ``main`` or ``foo_bar``).  There is always a
test list with ID ``main``; the active test list defaults to ``main`` but
can be changed in various ways (see :ref:`active-test-list`).

.. _active-test-list:

The active test list
--------------------
The file ``/usr/local/factory/py/test/test_lists/ACTIVE`` is used to
determine which test list is currently active.  This file contains the
ID of the active test list.  If this file is not present, the test
list with ID ``main`` is used.

If you want a different test list to be included by default, you
may simply create an ``ACTIVE`` file in the factory image.
The file should contain a single line of text: the ID
of the test list to activate.

In engineering mode in the test UI, the operator may select `Select
test list` from the main menu.  This will display all
available test lists.  Selecting one will clear all test state,
write the ID of the selected test list to the ``ACTIVE`` file, and
restart the test harness.

.. _test-paths:

Test IDs and paths
------------------
Within a test list, each node has an ID (like ``LTEModem`` or
``CalibrateTouchScreen``).  IDs do not have to be unique across the
entire test list, but they must be unique among all nodes that share
a parent.

To uniquely identify a node within a test list, each node has a
:index:`path` that is constructed by starting at the root and
concatenating all the node's IDs with periods.  Conceptually this is
very similar to how paths are formed in a UNIX file system (except
that UNIX file systems use slashes instead of paths) or in a Java
class hierarchy.  For example, if the ``LTEModem`` test in is a test
group called ``Connectivity``, then its path would be
``Connectivity.LTEModem``.

The "root node" is a special node that contains the top-level nodes
in the test list.  Its path is the empty string ``''``.

For instance, in :ref:`test-list-creation-sample`, the ``main``
test list contains nodes with the following paths:

* ``''`` (the root node)
* ``FirstTest``
* ``SecondTest``
* ``ATestGroup``
* ``ATestGroup.FirstTest``
* ``ATestGroup.SecondTest``

Logs and error messages generally contain the full path when referring
to a test, so you can easily identify which test the message is
referring to.

Declaring test lists
--------------------
.. note::

   Test lists were previously declared as single Python expressions,
   like ``TEST_LIST = [...]``, and placed in files called
   ``test_list`` for the main test list, or :samp:`test_list.{foo}`
   for a variant named "foo".  That type of test list is deprecated,
   and test lists are now declared in Python source files as described
   in the following documentation.

Each module in the
:py:mod:`cros.factory.test.test_lists` package can declare any number of
test lists.  There is a
generic test list in the :py:mod:`cros.factory.test.test_lists.generic`
module; this test list is used only if no other module in that directory
declares a test with with the ID ``main``.

In general, you will want to create the test list for your board by
copying the generic test list into your board overlay: use a file name
like
``private-overlays/overlay-foo/chromeos-base/chromeos-factory-board/file/py/test/test_lists/main.py``
to create a :py:mod:`cros.factory.test.test_lists.main` module there.

In order to declare test lists, your module must provide a
``CreateTestLists`` function that takes no arguments.  This function
can then call the building-block functions listed in
:ref:`test-list-building-block-functions` to create one or more test
lists.

Test lists are simply Python code, so you can modularize test list
creation by splitting it up into separate functions or modules.  Using
helper functions to create test lists may be very useful, for example,
to create test lists that are similar but contain certain differences
(e.g., some skipping certain tests or using different shop floor
configurations).

.. _test-list-creation-sample:

Test list creation sample
-------------------------
A sample module to create two test lists (``main`` and
``another_test_list``) follows::

  # Import factory_common to set up import paths.
  import factory_common
  # Import the necessary building blocks for creating test lists.
  from cros.factory.test.test_lists.test_lists import (
    FactoryTest,
    OperatorTest,
    TestGroup,
    TestList)

  # The function named CreateTestLists is invoked by the factory
  # test harness to declare test lists.
  def CreateTestLists():
    # Create the main test list (which must have id 'main').
    with TestList('main', 'Test List 1') as test_list:
      # First set various test list options.
      test_list.options.auto_run_on_start = False
      test_list.options.ui_lang = 'zh'

      # Now declare tests in the test list using FactoryTest,
      # OperatorTest, and TestGroup.
      FactoryTest(id='FirstTest', pytest_name='first_test')
      OperatorTest(id='SecondTest', pytest_name='second_test')
      with TestGroup(id='ATestGroup'):
        FactoryTest(id='FirstTest', ...)
        OperatorTest(id='SecondTest', ...)

    # Create another test list.
    with TestList('another_test_list', Another Test List') as test_list:
      FactoryTest(...)
      OperatorTest(...)

Note the following crucial parts:

* *Import statements* to import the necessary building-block functions from
  the :py:mod:`cros.factory.test.test_lists.main` module.
* A ``CreateTestLists`` function, which the test harness will invoke to
  create the test list.
* Within ``CreateTestLists``, a series of ``with TestList(...) as test_list``
  statements, each of which "opens" a new test list.
* Within the ``TestList`` contexts, statements to customize the test
  list options, as described in :ref:`test-list-options`.
* Also within the ``TestList`` contexts, statements to actually create the
  tests (``FactoryTest``, ``OperatorTest``, etc.).

Test arguments
--------------
It is often necessary to customize the behavior of various tests, such
as specifying the amount of time that a test should run, or which device
it should use.  For this reason, tests can accept arguments that modify
their functionality.

This arguments are passed as the ``dargs`` argument to one of the
building-block functions, e.g.::

  FactoryTest(id='Camera',
              pytest_name='camera',
              dargs=dict(face_recognition=False,
                         resize_ratio=0.7,
                         capture_resolution=(640, 480)))

A description of the permissible arguments for each test, and their
defaults, is included in the ``ARGS`` property in the class that
implements the test.

.. _test-list-building-block-functions:

Building-block functions
------------------------

.. py:module:: cros.factory.test.test_lists.test_lists

.. autofunction:: TestList(id, label_en)

.. autofunction:: FactoryTest

.. autofunction:: OperatorTest

.. autofunction:: TestGroup

.. _test-list-options:

Test list options
-----------------

.. py:module:: cros.factory.test.factory

.. autoclass:: Options
   :members:
