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
* A pytest, which is a test written using the standard Python unit test API.

Each test lists has an ID (like ``main`` or ``manual_smt``) that
describes what the test list does.  There is always a test list with
ID ``main``; the active test list defaults to ``main`` but this can be
changed in various ways (see :ref:`active-test-list`).

.. _active-test-list:

The active test list
--------------------
The file ``/usr/local/factory/py/config/active_test_list.json`` is used to
determine which test list is currently active.  This file contains the ID of
the active test list.  If this file is not present, then there are two ways to
determine the default test list;

* ID - ``main_${model}`` would be checked first where ``${model}`` is came from
  output of command - ``cros_config / name``.
* the test list with ID - ``main`` or ``generic_main`` is used.

If you want a different test list to be included by default, you
may simply add an argument ``--default-test-list <test-list-id>`` to the
factory toolkit installer while installing it to either a test image or a
device.

In engineering mode in the test UI, the operator may select `Select
test list` from the main menu.  This will display all
available test lists.  Selecting one will clear all test state,
write the ID of the selected test list to the ``active_test_list.json`` file,
and restart the test harness.

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
Each test list should be defined by a JSON file with file name
``<test_list_id>.test_list.json`` under ``py/test/test_lists/`` directory.  The
generic test list is defined by
``py/test/test_lists/generic_main.test_list.json``.

In general, when you start working on your own test list, you need to define
two test list files, ``common.test_list.json`` and ``main.test_list.json``.

``common.test_list.json``::

  {
    "inherit": [
      "generic_common.test_list"
    ],
    "constants": {
      # Common constants for your project.
    },
    "options": {
      # Common test list options for your project.
    },
    "definitions": {
      # Define new pytests, or override pytest arguments.
    }
  }

``main.test_list.json``::

  {
    "inherit": [
      "common.test_list",
      "generic_main.test_list"
    ],
    "constants": {
      # Constants for this test list.
    }
    "options": {
      # Options for this test list.
    },
    "definitions": {
      "FATItems": [
        # Redefine FATItems (adding, removing, reordering)
      ],
      ...
    }
  }

.. _test-list-creation-sample:

Test list creation sample
-------------------------
Board specific test lists should be placed in board overlay
(:samp:`src/private-overlays/overlay-{board}-private/chromeos-base/factory-board/files/py/test/test_lists/`).
And they should reuse test lists in public repository (i.e.
``generic_*.test_list.json``).

For example ``common.test_list.json``::

  {
    "inherit": [
      "generic_common.test_list"
    ],
    "constants": {
      "allow_force_finalize": [],  # Not allowed.
      "enable_factory_server": true,
      "led_colors": [
        "WHITE",
        "AMBER",
        "OFF"
      ],
      "lid_switch_event_id": 1,
      "light_sensor_input": "in_illuminance_input",
      "min_release_image_version": "9777.0",
      "sysfs_path_sd": "/sys/devices/pci0000:00/0000:00:1e.6/mmc_host/",
      "typec_usb": {
        "left": {
          "usb2_sysfs_path": "/sys/devices/pci0000:00/0000:00:14.0/usb1/1-1",
          "usb3_sysfs_path": "/sys/devices/pci0000:00/0000:00:14.0/usb2/2-1",
          "usbpd_id": 0,
          "display_info": [
            "DisplayPort",
            "DP-1"
          ]
        },
        "right": {
          "usb2_sysfs_path": "/sys/devices/pci0000:00/0000:00:14.0/usb1/1-5",
          "usb3_sysfs_path": "/sys/devices/pci0000:00/0000:00:14.0/usb2/2-2",
          "usbpd_id": 1,
          "display_info": [
            "DisplayPort",
            "DP-2"
          ]
        }
      }
    }
  }

Sample ``main.test_list.json``::

  {
    "inherit": [
      "common.test_list",
      "generic_main.test_list"
    ],
    "constants": {
      "default_factory_server_url": "http://192.168.111.222:8888/"
    },
    "options": {
      "skipped_tests": {
        "PROTO": [
          "*.AudioJack",
          "*.SpeakerDMic"
        ]
      }
    }
  }

Note the following crucial parts:

* ``options`` is a dictionary that defines test list options, as described in
  :ref:`test-list-options`.

Test arguments
--------------
It is often necessary to customize the behavior of various tests, such
as specifying the amount of time that a test should run, or which device
it should use.  For this reason, tests can accept arguments that modify
their functionality.

Most pytests should already be defined by ``generic_common``, you only need to
override test arguments.  For example, in your ``common.test_list.json``::

  {
    ...,
    "definitions": {
      "QRScan": {
        "args": {
          # Only override "camera_args".
          "camera_args": {
            "resolution": [
              1280,
              720
            ]
          }
        }
      }
    }
  }

In this case, test arguments for QRScan will be::

  {
    # defined by generic_common.test_list.json
    "mode": "qr",
    "QR_string": "Hello ChromeOS!",
    # defined by common.test_list.json
    "camera_args": {
      "resolution": [
        1280,
        720
      ]
    }
  }

If you want to **replace** ``args`` completely, instead of updating, you should
use ``__replace__`` keyword::

  {
    ...,
    "definitions": {
      "QRScan": {
        "args": {
          "__replace__": true,
          # definitions in generic_common will be disgarded
          ...
        }
      }
    }
  }

A description of the permissible arguments for each test, and their
defaults, is included in the ``ARGS`` property in the class that
implements the test.

.. _test-list-options:

Test list options
-----------------

.. py:module:: cros.factory.test.test_lists.test_list

.. autoclass:: Options
   :members:
