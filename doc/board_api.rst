Board API
=========

If you need to implement test behavior in a board-specific way, use or
extend :py:class:`cros.factory.system.board.Board`.  This class
provides board-specific functionality, e.g.:

- forcing device charge state
- observing on-board sensors such as temperature sensors
- querying the EC (embedded controller)
- directly reading/writing values over the I2C bus

Obtaining a Board object
------------------------
To obtain a :py:class:`cros.factory.system.board.Board` object for the
device under test, use the following function:

.. py:module:: cros.factory.system

.. autofunction:: GetBoard

.. _board-api-extending:

Extending the Board class
-------------------------
The :py:class:`cros.factory.board.chromeos_board.ChromeOSBoard` class
is the default implementation of :py:class:`cros.factory.system.board.Board`,
but you may find that you need to customize or override certain functionality
for your project. To do so:

#. Define a new subclass of :py:class:`cros.factory.system.board.Board`
   in the :py:mod:`cros.factory.board` package.  In general, for a board
   named :samp:`{xxx}`, you will add a
   file :samp:`private-overlays/overlay-{xxx}-private/chromeos-base/chromeos-factory-board/files/py/board/{xxx}_board.py`
   containing the following::

     import factory_common  # pylint: disable=W0611

     from cros.factory.board.chromeos_board import ChromeOSBoard
     from cros.factory.system.board import Board, BoardException

     class XxxBoard(ChromeOSBoard):
       # ... implement/override methods here ...

   Generally, your class should be derived from the
   :py:class:`cros.factory.board.chromeos_board.ChromeOSBoard` class, but if your
   device has no EC or a standard EC, you may wish to directly subclass
   :py:class:`cros.factory.system.board.Board`.

#. Specify that your implementation should be used.  To do this, in
   :samp:`private-overlays/overlay-{board}-private/chromeos-base/chromeos-factory-board/files/board/board_setup_factory.sh`,
   add a line like the following::

     export CROS_FACTORY_BOARD_CLASS="cros.factory.board.xxx_board.XxxBoard"

Adding new methods to the Board class
-------------------------------------
If you need to perform some system operation in a highly CrOS-specific
or board-specific way, you may need to add a new method to the
:py:class:`cros.factory.system.board.Board` class.

Let's say that you're working on a cool new CrOS device ("mintyfresh")
with a built-in air freshener, and you need to write a test for this
game-changing new component.  Consider the following questions:

- **Is there a standard way of controlling the air freshener component
  in a way that should work for all present and future devices?**  (For
  example, you can activate and deactivate the component by writing
  ``1`` or ``0`` to ``/sys/module/airfreshener/active``, or calling a
  user-level program ``airfreshenerctl enable``.)

  In this case there is no reason to add a method to
  :py:class:`cros.factory.system.board.Board`, since no one will ever
  need to override it.  Simply add a new function
  ``SetAirFreshenerActive(active)`` to one of the utility modules in
  :py:mod:`cros.factory.util`; or if the component is better
  encapsulated perhaps a new wrapper class
  :py:class:`cros.factory.system.air_freshener.AirFreshener`.

- **Is there a mostly standard way of controlling the air freshener
  across CrOS devices, but that might be different for certain
  devices?** (For instance, you can call ``ectool airfreshener 1`` to
  enable the air freshener, but CrOS devices with a non-standard EC
  may need to implement this differently.)

  In this case, add an abstract method to
  :py:class:`cros.factory.system.board.Board` and a default
  implementation in
  :py:class:`cros.factory.board.chromeos_board.ChromeOSBoard`; it will
  work for "standard" devices but can be overridden as necessary.

- **Is the functionality totally one-off for your device?** (For instance,
  you need to control the device via a hard-coded register on the I2C bus.)

  If so, add an abstract method to
  :py:class:`cros.factory.system.board.Board` and provide the
  implementation directly in your
  :py:class:`cros.factory.board.MintyFreshBoard` class.  Don't provide
  an implementation in
  :py:class:`cros.factory.board.chromeos_board.ChromeOSBoard`, since
  it wouldn't be useful on other boards anyway.

- **Is the functionality confidential?**

  If so, simply implement your functionality in
  :py:class:`cros.factory.board.MintyFreshBoard`.  Once the device is
  launched, add a method to
  :py:class:`cros.factory.system.board.Board` and move your
  implementation to
  :py:class:`cros.factory.board.chromeos_board.ChromeOSBoard` so it
  can be re-used for future devices.


API Documentation
-----------------

.. py:module:: cros.factory.system.board

.. autoclass:: Board
   :members:

.. py:module:: cros.factory.board.chromeos_board

.. autoclass:: ChromeOSBoard
