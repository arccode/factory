.. _test-ui-api:

Test UI API
===========
The Test UI API allows tests to interact with an operator, or to
display their status to the operator while they are running.

To use the test UI, inherit from
:py:class:`cros.factory.test.test_ui.TestCaseWithUI` instead of
:py:class:`unittest.TestCase` for the unittest. You can then call various
methods on ``self.ui`` and ``self.template`` to interact with the browser (see
`Test UI Class Reference`_ and `Test UI Templates`_).

For example, this test displays "Hello, world" in the UI, waits
five seconds, and then passes::

  import time
  from cros.factory.test import test_ui

  class MyTest(test_ui.TestCaseWithUI):
    def runTest(self):
      self.template.SetState('Hello, world!')
      time.sleep(5)

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

Pass or fail the test
---------------------
To fail the test, do one of the followings:

* Calls ``window.test.fail(msg)`` in JavaScript implementation.
* Calls ``self.ui.Fail(error_msg)`` in any thread of the Python implementation.
* Raises exception in ``runTest`` (Can be exception raised by calling various
  ``self.assert*`` methods from ``unittest.TestCase``).

To pass the test, do one of the followings:

* Calls ``window.test.pass()`` in JavaScript implementation.
* Calls ``self.ui.Pass()`` in any thread of the Python implementation.
* If nothing fails the test, the test is **automatically passed after**
  ``runTest`` **return**. To wait for either ``Pass`` or ``Fail`` is called in
  event handler, call ``self.WaitTaskEnd()`` at the end of ``runTest``, and the
  test would wait for one of the conditions above is achieved.

When the test inherits from ``TestCaseWithUI``, the ``runTest`` method is run
in a **background** thread, while the UI event loop run in the main thread.
This also means that the test never need to call ``self.ui.Run`` or
``self.ui.RunInBackground`` since they're handled in the parent class.

Test UI Class Reference
-----------------------
.. py:module:: cros.factory.test.test_ui

.. autoclass:: UI
   :members:

.. _test-ui-templates:

Test UI Templates
-----------------
Rather than building your UI entirely from scratch, there are templates that
you may find useful to keep look and feel consistent across tests.

By default, tests inherit from ``test_ui.TestCaseWithUI`` would use the
`One-section template`_. To change what template to be used, override the class
variable ``template_type``. For example::

  from cros.factory.test import test_ui

  class MyTest(test_ui.TestCaseWithUI):
    template_type = 'two-sections'

    def runTest(self):
      self.template.SetTitle('My Test')
      self.template.SetState('Hello, world!')
      ...

One-section template
````````````````````
.. py:module:: cros.factory.test.ui_templates

.. autoclass:: OneSection
   :inherited-members:
   :members:

One-scrollable-section template
```````````````````````````````
.. autoclass:: OneScrollableSection
   :inherited-members:
   :members:

Two-section template
````````````````````
.. autoclass:: TwoSections
   :inherited-members:
   :members:
