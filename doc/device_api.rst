Device-Aware API and Board
==========================

If you need to implement test behavior for device (DUT or station) in a
board-specific way, use or extend
:py:class:`cros.factory.device.device_types.DeviceBoard`.  This class provides
board-specific functionality, e.g.:

- forcing device charge state
- observing on-board sensors such as temperature sensors
- querying the EC (embedded controller)
- directly reading/writing values over the I2C bus

Obtaining a Board object
------------------------
To obtain a :py:class:`cros.factory.device.device_types.DeviceBoard` object for
the device under test, use the following function:

.. py:module:: cros.factory.device.device_utils

.. autofunction:: CreateDUTInterface
.. autofunction:: CreateStationInterface

.. _board-api-extending:

Extending the Board class
-------------------------
The base implementation of all boards is
:py:class:`cros.factory.device.device_types.DeviceBoard`. Currently if
board_class is not specified, device_utils.CreateDUTInterface() function will
return an instance of interface for ChromeOS devices using the subclass
:py:class:`cros.factory.device.boards.chromeos.ChromeOSBoard`.  However, you may
find that you need to customize or override certain functionality for your
project. To do so:

#. Define a new subclass of
   :py:class:`cros.factory.device.boards.chromeos.ChromeOSBoard`
   in the :py:mod:`cros.factory.device.boards` package.  In general,
   for a board named :samp:`{xxx}`, you will add a
   file :samp:`private-overlays/overlay-{xxx}-private/chromeos-base/factory-board/files/py/device/boards/{xxx}.py`
   containing the following::

     from cros.factory.device.boards import chromeos
     from cros.factory.device import device_types
     from cros.factory.utils import type_utils


     # Implement or import and override the components with difference.
     class XxxPower(types.DeviceComponent):

       def DoSomething(self):
         pass


     class XxxBoard(chromeos.ChromeOSBoard):
       # ... implement/override methods here ...

       @type_utils.Overrides
       @types.DeviceProperty
       def power(self):
         return XXXPower(self)


   Generally, your class should be derived from the
   :py:class:`cros.factory.device.boards.chromeos.ChromeOSBoard` class, but
   if your device is not ChromeOS, you may wish to directly subclass
   :py:class:`cros.factory.device.boards.android.AndroidBoard` or
   :py:class:`cros.factory.device.device_types.DeviceBoard`.

#. Specify that your implementation should be used.  To do this, in
   :samp:`private-overlays/overlay-{board}-private/chromeos-base/factory-board/files/py/config/devices.json`,
   write a JSON configuration to specify the type of board and link to use just
   like the following::

     {"dut": {"board_class": "XXXBoard", "link_class": "XXXLink"}}

   `board_class` refers to the class name under `cros.factory.device.boards`,
   and `link_class` refers to the class name under `cros.factory.device.links`.

Adding new modules to the Board class
-------------------------------------
If you need to perform some system operation in a highly CrOS-specific
or board-specific way, you may need to add a new property or method to the
:py:class:`cros.factory.device.device_types.DeviceBoard` class.

Let's say that you're working on a cool new CrOS device ("mintyfresh")
with a built-in air freshener, and you need to write a test for this
game-changing new component.  Consider the following questions:

- **Is there a mostly standard way of controlling the air freshener
  across CrOS devices, but that might be different for certain
  devices?** (For instance, you can call ``ectool airfreshener 1`` to
  enable the air freshener, but CrOS devices with a non-standard EC
  may need to implement this differently.)

  In this case, add an abstract module ``airfreshener.py`` to
  :py:mod:`cros.factory.device` and include that in
  :py:class:`cros.factory.device.device_types.DeviceBoard` as a new
  DeviceProperty ``airfreshener``.
  it will work for "standard" devices but can be overridden as necessary.

- **Is the functionality totally one-off for your device?** (For instance,
  you need to control the device via a hard-coded register on the I2C bus.)

  If so, add an abstract method to
  :py:class:`cros.factory.device.device_types.DeviceBoard` and provide the
  implementation directly in your
  :py:class:`cros.factory.device.boards.mintyfresh.MintyFreshBoard` class.
  Don't provide an implementation in
  :py:class:`cros.factory.device.boards.chromeos.ChromeOSBoard`, since
  it wouldn't be useful on other boards anyway.

- **Is the functionality confidential?**

  If so, simply implement your functionality in
  :py:class:`cros.factory.device.boards.mintyfresh.MintyFreshBoard`.
  Once the device is launched, add a method to
  :py:class:`cros.factory.device.device_types.DeviceBoard` and move your
  implementation to
  :py:class:`cros.factory.device.boards.chromeos.ChromeOSBoard` so it
  can be re-used for future devices.


API Documentation
-----------------

.. py:module:: cros.factory.device.device_types

.. autoclass:: DeviceBoard
   :members:
   :inherited-members:

.. autoclass:: DeviceLink
   :members:
