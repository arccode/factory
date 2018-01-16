.. _test-ui-api:

Test UI API
===========
The Test UI API allows tests to interact with an operator, or to
display their status to the operator while they are running.

To use the test UI, inherit from
:py:class:`cros.factory.test.test_case.TestCase` instead of
:py:class:`unittest.TestCase` for the unittest. You can then call various
methods on ``self.ui`` (which is of type
:py:class:`cros.factory.test.test_ui.StandardUI`) to interact with the browser
(see `Test UI Class Reference`_).

For example, this test displays "Hello, world" in the UI, waits
five seconds, and then passes::

  import time
  from cros.factory.test import test_ui

  class MyTest(test_case.TestCase):
    def runTest(self):
      self.template.SetState('Hello, world!')
      self.Sleep(5)

The following document assumes that the test inherit from
:py:class:`cros.factory.test.test_case.TestCase`.

See :ref:`test-i18n-api` on how to display localized texts on UI.

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

In addition, these files will be automatically loaded if they exist:

* :samp:`py/test/pytests/{mytest}_static/{mytest}.html`
* :samp:`py/test/pytests/{mytest}_static/{mytest}.js`
* :samp:`py/test/pytests/{mytest}_static/{mytest}.css`

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
* :samp:`py/test/pytests/{mytest}/static/{mytest}.css`

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

Pass or fail the test
---------------------
To fail the test, do one of the followings:

* Calls ``window.test.fail(msg)`` in JavaScript implementation.
* Raises exception in either ``runTest`` or in the event handlers (Can be
  exception raised by calling various ``self.assert*`` methods from
  ``unittest.TestCase``).
* Calls ``self.FailTask(error_msg)``, which is exactly the same as ``raise
  type_utils.TestFailure(error_msg)``.

To pass the test, do one of the followings:

* Calls ``window.test.pass()`` in JavaScript implementation.
* Calls ``self.PassTask()`` in either ``runTest`` or in the event handlers.
* If nothing fails the test, the test is **automatically passed after**
  ``runTest`` **return**. To wait for either pass or fail is explictly called,
  call ``self.WaitTaskEnd()`` at the end of ``runTest``, and the test would
  wait for one of the conditions above is achieved.

When the test inherits from ``test_case.TestCase``, the ``runTest`` method is
run in a **background** thread, while the UI event loop run in the main thread.

The ``PassTask``, ``FailTask`` and raises exception to fail test only works in
either event handlers or in the ``runTest`` thread. To achieve same behavior on
other threads, wrap the function with ``self.event_loop.CatchException``. For
example::

  def BackgroundWork(self):
    # Background works that have to be done in another thread.

  def runTest(self):
    thread = process_utils.StartDaemonThread(
        target=self.event_loop.CatchException(self.BackgroundWork))
    # Do some other things in parallel with BackgroundWork.

Test UI Templates
-----------------
There are default templates for test to keep look and feel consistent across
tests. To access the template, use methods on
:py:class:`cros.factory.test.test_ui.StandardUI`. For example::

  class MyTest(test_case.TestCase):
    def runTest(self):
      self.ui.SetTitle('My Test')
      self.ui.SetState('Hello, world!')
      ...

To change what UI class is used for ``self.ui``, set the ``ui_class`` for the
test class. For example::

  class MyTest(test_case.TestCase):
    ui_class = test_ui.ScrollableLogUI

    def runTest(self):
      self.ui.AppendLog('some log')

Test UI Class Reference
-----------------------
.. py:module:: cros.factory.test.test_ui

.. autoclass:: UI
   :members:

.. autoclass:: StandardUI
   :members:
