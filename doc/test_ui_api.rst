.. _test-ui-api:

Test UI API
===========
The Test UI API allows tests to interact with an operator, or to
display their status to the operator while they are running.

To use the test UI, create a :py:class:`cros.factory.test.test_ui.UI`
object in your test, generally within the ``setUp`` method of your
test case. Save the UI object as an attribute of your test case
(``self.ui``). You can then call various methods on this object to
interact with the browser (see `Test UI Class Reference`_).

For example, this test displays "Hello, world" in the UI, waits
five seconds, and then passes::

  import time
  import unittest
  from cros.factory.test import test_ui

  class MyTest(unittest.TestCase)::
    def setUp(self):
      self.ui = test_ui.UI()

    def runTest(self):
      self.ui.Run(blocking=False)
      self.ui.SetHTML('Hello, world!')
      time.sleep(5)

Rather than building your UI entirely from scratch, there are some
templates that you may find useful to keep look and feel consistent
across tests. For more information, see :ref:`test-ui-templates`.

Including static resources
--------------------------
Often you will want to include static resources, such as images, HTML,
and JavaScript code, in your UI. Where to put static resources
depends on how you have laid out your test directory.

Simple layout
`````````````
If your test is called :samp:`{mytest}` and your test code is in the
file :samp:`py/test/pytests/{mytest}.py`, you may include static
resources in a directory called

  :samp:`py/test/pytests/{mytest}_static`

In addition, when the ``UI`` class is created, any of the following
will be automatically loaded if they exist:

* :samp:`py/test/pytests/{mytest}.html`
* :samp:`py/test/pytests/{mytest}.js`
* :samp:`py/test/pytests/{mytest}_static/{mytest}.html`
* :samp:`py/test/pytests/{mytest}_static/{mytest}.js`

Nested layout
`````````````
If your test has its own subdirectory (i.e., your test code is in
:samp:`py/test/pytests/{mytest}/{mytest}.py`), then you can create a
``static`` directory within your test's subdirectory, and put static
resources there:

  :samp:`py/test/pytests/{mytest}/static`

In addition, these files will be automatically loaded if they exist:

* :samp:`py/test/pytests/{mytest}/static/{mytest}.html`
* :samp:`py/test/pytests/{mytest}/static/{mytest}.js`

Referring to static resources
`````````````````````````````
Within your UI, you can refer to static resources with relative
paths. For instance, if you have a file called ``foo.png`` in your
static directory:

  :samp:`py/test/pytests/{mytest}/static/foo.png`

You may simply use this HTML to refer to the image:

  ``<img src="foo.png">``

Alternatively, you can use an absolute path:

  :samp:`<img src="/tests/{mytest}/foo.png">`

Threading models
----------------
You can use one of two threading models to run the UI. Most tests
should use the non-blocking (Python-centric) threading model.

1. *Non-blocking (Python-centric) threading model*. At the beginning
   of your ``runTest`` method, call
   ``self.ui.Run(blocking=False)``. This will cause the UI to run in the
   background. The test will terminate whenever ``runTest`` returns
   (in which case the test passes), or throws an exception (in which
   case the test fails).

   This threading model is most useful when, as with most tests, the
   bulk of the test logic is implemented in Python, and it is the
   Python code that determines whether the test should pass or
   fail.

   In this case there is no need to call ``self.ui.Pass()`` or
   ``self.ui.Fail(error_msg)``; the pass/fail condition is determined
   solely by whether ``runTest`` returns cleanly, as in most Python
   unit tests.

2. *Blocking (UI-cetric) threading model*. At the *end* of your
   ``runTest`` method, call ``self.ui.Run(blocking=True)``. This
   will block until one of the following things happens:

   a. JavaScript code in your UI implementation calls
      ``window.test.pass()``. (``window.test.pass`` and
      ``window.test.fail`` are JavaScript
      methods provided in the UI by the test harness.)
   b. JavaScript code in your UI implementation calls ``window.test.fail(msg)``.
   c. Any thread in your Python test implementation calls
      ``self.ui.Pass()``.
   d. Any thread in your Python test implementation calls
      ``self.ui.Fail(error_msg)``.

   In passing cases (a) and (c), ``Run()`` simply returns; your
   ``runTest`` method will then return and the test will end
   successfully.

   However, in failing cases (b) and (d), ``Run()`` raises an
   exception, which propagates from ``runTest`` and causes your
   test to fail.

   This threading model is most useful when most of the test logic is
   implemented in the UI itself, and it is the UI that "decides"
   whether the test should pass or fail.

Test UI Class Reference
-----------------------
.. py:module:: cros.factory.test.test_ui

.. autoclass:: UI
   :members:

.. _test-ui-templates:

Test UI Templates
-----------------
Rather than building your UI entirely from scratch, there are two
templates that you may find useful to keep look and feel consistent
across tests.  To use a template, create a template object, using the
:py:class:`cros.factory.test.test_ui.UI` as an argument.  You can then
call methods on the template object to manipulate the UI.  For
example::

  from cros.factory.test import test_ui
  from cros.factory.test import ui_templates

  class MyTest(unittest.TestCase)::
    def setUp(self):
      self.ui = test_ui.UI()
      self.template = ui_templates.TwoSections(self.ui)

    def runTest(self):
      self.template.SetTitle('My Test')
      self.template.SetState('Hello, world!')
        ...

Two-section template
````````````````````
.. py:module:: cros.factory.test.ui_templates

.. autoclass:: TwoSections
   :inherited-members:
   :members:

One-section template
````````````````````
.. autoclass:: OneSection
   :inherited-members:
   :members:

One-scrollable-section template
```````````````````````````````
.. autoclass:: OneScrollableSection
   :inherited-members:
   :members:
