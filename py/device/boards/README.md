Device API: Boards Implementation
=================================
This folder contains implementations for different boards.

To add your own class, inherit from one board and override your `Device`
properties:

    from cros.factory.device import types
    from cros.factory.device import power

    class MyPower(power.Power):
      def CheckACPresent(self):
        return False

    class MyBoard(types.DeviceBoard):

      @types.DeviceProperty
      def power(self):
        return MyPower(self)
