Introduction to working with the Factory SDK
============================================

Layout
------

The factory repository contains the following important
files and directories:

* ``bin``: Symlinks to variables tools and utilities within the
  factory source.
* ``build``: A temporary directory used when building the factory
  SDK.
* ``Makefile``: Used to build the factory code and documentation.
* ``py``: Python source.  The "root" of this source tree is the
  :py:mod:`cros.factory` module, so for instance the module
  :py:mod:`cros.factory.system.board` would be found in the
  ``py/system/board`` directory.
* ``py_pkg``: A directory that is used as the ``PYTHONPATH`` entry to
  include the factory source.  ``py_pkg/cros/factory`` is simply a
  symlink to the ``py`` directory, so when Python searches for (e.g.)
  the :py:mod:`cros.factory.system.board` module, it will find it in
  ``py_pkg/cros/factory/system/board.py`` (which points to
  ``py/system/board.py``).
* ``sh``: Shell scripts.
* ``test_lists``: Old-style test lists.  (New test lists are simply
  code in the :py:mod:`cros.factory.test.test_lists` module.  See
  :ref:`declaring-test-lists`.)

Makefile
--------
Make targets include:

* ``default``: Builds the factory test harness.
* ``par``: Builds a par file ("Python archive") that contains the
  entire source and dependent libraries, and can be used to run
  various tools and utilities.
* ``lint``: Checks the source for style violations.
* ``test``: Runs unit tests.
* :samp:`overlay-{board}`: Creates a directory called `overlay-{board}`
  containing the contents of the factory source, overlayed with contents
  from the board overlay (e.g., in
  :samp:`third_party/private-overlays/overlay-{board}-private/chromeos-board/factory-board/files`).
  This is useful to pull in board-specific files such as test lists.
* :samp:`overlay-{board}-lint`: Runs the :samp:`overlay-{board}-lint`
  target, and further runs ``make lint`` within the overlay directory.
* :samp:`overlay-{board}-test`: Runs the :samp:`overlay-{board}-test`
  target, and further runs ``make test`` within the overlay directory.

In general, it is advisable to run ``make lint`` and ``make test`` before submitting
code. There are presubmit checks to enforce this.

If you are working on board overlays, it is also a good idea to run
:samp:`make overlay-{board}-lint`, and possibly :samp:`make
overlay-{board}-test`, to verify that any files you have changed in
the board overlay are syntatically correct and have no style violations.

Coding style
------------
Make sure to follow the `Chromium Python Style Guide
<https://chromium.googlesource.com/chromiumos/docs/+/HEAD/styleguide/python.md>`_.

In the factory repository, we also try to follow the `Google Python
Style Guide
<http://google-styleguide.googlecode.com/svn/trunk/pyguide.html>`_ as
much as possible. If there is a conflict between the two, the Chromium
Python Style Guide wins.

Unit testing
------------
Source files with filenames ending in ``_unittest.py`` are considered
to be unit tests.  All such tests are run by the ``test`` Makefile
target (``make test``).

You can put unit tests in the board overlay as well; these tests can
be run by :samp:`make overlay-{board}-test`.
