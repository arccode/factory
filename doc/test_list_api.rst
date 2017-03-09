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

Each test lists has an ID (like ``main`` or ``manual_smt``) that
describes what the test list does.  There is always a test list with
ID ``main``; the active test list defaults to ``main`` but this can be
changed in various ways (see :ref:`active-test-list`).

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
that UNIX file systems use slashes instead of periods) or in a Java
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

.. _declaring-test-lists:

Declaring test lists
--------------------
.. note::

   Test lists were previously declared as single Python expressions,
   like ``TEST_LIST = [...]``, and placed in files called
   ``test_list`` for the main test list, or :samp:`test_list.{foo}`
   for a variant named "foo".  That type of test list is deprecated,
   and test lists are now declared in Python source files as described
   in the following documentation.

   See :ref:`converting-test-lists` for more information.

Each module in the
:py:mod:`cros.factory.test.test_lists` package can declare any number of
test lists.  There is a
generic test list in the :py:mod:`cros.factory.test.test_lists.generic`
module; this test list is used only if no other module in that directory
declares a test with with the ID ``main``.

In general, you will want to create the test list for your board by
copying the generic test list into your board overlay: use a file name
like
``private-overlays/overlay-foo/chromeos-base/factory-board/files/py/test/test_lists/main.py``
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

.. _adding-a-new-test-list:

Adding a new test list
----------------------
To add a new new-style test list, you have two options:

* **Create a brand new module.** The module must be in the
  :py:mod:`cros.factory.test.test_lists` package. Within the source
  tree, you can do this in one of two places:

  * In the public repo (:samp:`platform/factory/py/test/test_lists/{test_list_name}.py`).
    Naturally, this test list would apply to all boards.

  * In the board overlay
    (:samp:`src/private-overlays/overlay-{board}-private/chromeos-base/factory-board/files/py/test/test_lists/{test_list_name}.py`).

  Note that the module name (:samp:`{test_list_name}` in the examples
  above) is not necessarily the test list's ID: since a single module
  can define any number of test lists, you must specify the test
  list's ID as an argument to the ``TestList`` function, not as the
  module name. If you're only defining one test list in your module,
  though, it's probably a good idea to use the ID as the module name.

  You could start by just copy-and-pasting an existing test list and
  changing its ID, but of course this has the big caveat that it will
  permanently diverge from the main test list! If you want to keep
  multiple test lists "in sync", you'll probably want to choose the
  next option.

* **Create a variant of an existing test list.** You can factor the
  commonalities between the test lists out into separate functions
  or modules, which you can then re-use.

  This is obviously harder than copy-and-pasting, since you have to
  think carefully about how to characterize the differences between
  test lists. Sometimes copy-and-pasting will be the right approach
  (e.g., for quick hacks), but carefully parameterizing your test
  lists may be worth the extra effort for code reuse.

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

.. _converting-test-lists:

Converting old-style test lists
-------------------------------
In the past, each test list was a single giant Python expression. This
gave rise to a number of problems:

* It was hard to add conditional logic to create test list variants.

* It was hard to pinpoint syntax errors in tests (am I missing a
  parenthesis? where?)

* It was hard to find logic errors and typos, since test lists are not
  lint-able.

* It was hard to factor test lists as re-usable code.

The main differences between the old and new format are:

* Rather than being single expressions, test lists are now Python code
  within a ``CreateTestLists()`` function.  They can now comprise
  multiple statements, which means that they can be decomposed into
  multiple modules and functions, and it is easy to reuse code to
  create test lists that vary in well-defined ways.

* You use ``with TestList(...)`` instead of ``TEST_LIST = [`` to "open"
  a test list.

* To define nested tests, you use the ``with`` keyword rather than
  the ``subtests`` argument.  For example, this::

     FactoryTest(id='SMT', subtests=[
       FactoryTest(id='A', ...),
       FactoryTest(id='B', ...),
       ...
     ]

  becomes this::

    with FactoryTest(id='SMT'):
      FactoryTest(id='A', ...)
      FactoryTest(id='B', ...)

To convert from an old-style to new-style test list, here's the basic
idea:

#. Create a new module in the :py:mod:`cros.factory.test.test_lists`
   package (that's the ``py/test/test_lists directory``).
   Copy-and-paste your test list to the new file.

#. Put this at the top of your test list (replacing ``test_list_id`` and
   ``Test List Description`` as appropriate)::

      import factory_common
      # Import the necessary building blocks for creating test lists.
      from cros.factory.test.test_lists.test_lists import (
        FactoryTest,
        OperatorTest,
        TestGroup,
        TestList)

      def CreateTestLists():
        with TestList('test_list_id', 'Test List Description'):
          ...old test list contents goes here...

#. Remove ``TEST_LIST_NAME``; it's not used anymore (put the name in
   the ``TestList`` statement above).

#. Get rid of the ``TEST_LIST = [`` line (and the matching ``]`` at the
   end).  Whenever you see the ``subtests`` keyword, change the line to
   start with ``with`` instead, and indent the subtests within the
   enclosing context.

To make sure that your old and new test lists, are identify, you can use
the ``factory dump-test-list`` command as follows:

#. Before starting to convert your test list, run :samp:`make
   overlay-{board}` to make a complete copy of the public repository,
   overlaid with the private repository, in the
   :samp:`overlay-{board}` directory.  Then run
   :samp:`overlay-{board}/bin/factory dump-test-list
   {old_test_list_id} > /tmp/old.yaml` to obtain a complete dump of
   the old test list as a YAML document.  The format of this dump is
   not important, but its contents can be compared to the dump from
   your new test list.

#. As you convert your test list, run :samp:`make overlay-{board} ;
   overlay-{board}/bin/factory dump-test-list {new_test_list_id} >
   /tmp/new.yaml`.  You can then compare the contents of
   ``/tmp/old.yaml`` and ``/tmp/new.yaml`` (e.g., by running ``diff -u
   /tmp/old.yaml /tmp/new.yaml``) to see if there are any functional
   differences between your old and new test lists.
