# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""ShopFloorHandlerBase: The base class of per board ShopFloorHandler.

See ShopFloorHandlerBase class comments for detail.
"""


RPC_METHOD_ATTRIBUTE = 'is_rpc_method'


def RPCCall(method):
  """Decorator that enables the method to be XML RPC method.

  Example:
    class FooServer(object):
      def NonRPCFunction():
        ...

      @RPCCall
      def RPCFunction(parameter, ...):
        ...

    Then RPCFunction becomes XMLRPC method for:
      FastCGIServer(ip, port, FooServer())

  Args:
    method: a class method.

  Returns:
    decorated method with is_rpc_method attrubute set to True.
  """
  setattr(method, RPC_METHOD_ATTRIBUTE, True)
  return method


class ShopFloorHandlerException(Exception):
  pass


class ShopFloorHandlerBase(object):
  """The base class of per board ShopFloorHandler.

  Each board (or factory) must have its own [board/ODM]ShopFloorHandler to
  proxy shop floor request from DUT to the shop floor server of the factory.

  Its serving path is "/shop_floor/<port>/<token>", which can be obtained
  from DUT resource map.

  Each RPC call raises KeyError if an input parameter is invalid, e.g.
  invalid serial_number. For the rest of errors, raises
  ShopFloorHandlerException instead, like: ShopFloorHandlerException(
     'Unable to communicate with the shop floor server').
  """

  def __init__(self):
    super(ShopFloorHandlerBase, self).__init__()

  @RPCCall
  def GetMLBInfo(self, mlb_sn, operator_id):
    """Gets the expected configuration of the MLB (motherboard) to test.

    Obtains information about the expected configuration of the MLB. The shop
    floor server also checks that the MLB SN and operator ID are valid.

    It should be called at the beginning of the SMT test.

    Args:
      mlb_sn: The motherboard serial number.
      operator_id: The operator ID.

    Returns:
      A dictionary containing the expected configuration of the MLB.
    """
    raise NotImplementedError()

  @RPCCall
  def FinishSMT(self, mlb_sn, operator_id, report_blob_xz=None):
    """Informs that the MLB finishes SMT tests.

    Once it is invoked and succeeds, GetMLBInfo and FinishSMT shall never
    success again for this MLB, even if the MLB is re-imaged.

    Args:
      mlb_sn: The motherboard serial number.
      operator_id: The operator ID.
      report_blob_xz: The xzipped report blob (optional).
    """
    raise NotImplementedError()

  @RPCCall
  def GetDeviceInfo(self, mlb_sn):
    """Gets the expected configuration of the DUT (device under test).

    Obtains information about the expected configuration of the DUT from the
    shop floor server. The shop floor server also checks that the DUT
    mlb_sn and serial_number are valid.

    Args:
      mlb_sn: The motherboard serial number.

    Returns:
      A dictionary containing the expected configuration of the DUT.
    """
    raise NotImplementedError()

  @RPCCall
  def FinishHWID(self, serial_number):
    """Informs the shop floor server that HWID verification is complete.

    Args:
      serial_number: The DUT's serial number.
    """
    raise NotImplementedError()

  @RPCCall
  def FinishFA(self, serial_number, device_data):
    """Informs that the DUT finishes FA tests.

    The DUT is about to be finalized. It also saves the
    device_data to persistent storage for later uploading to Google.

    Args:
      serial_number: The DUT's serial number.
      device_data: The complete device data dictionary (which must
        include fields: 'serial_number', 'hwid', 'ubind_attribute', and
        'gbind_attribute').
    """
    raise NotImplementedError()

  @RPCCall
  def Finalize(self, serial_number):
    """Informs that the DUT is ready for shipment.

    Args:
      serial_number: The DUT's serial number.
    """
    raise NotImplementedError()

  @RPCCall
  def GetRegistrationCodeMap(self, serial_number):
    """Returns the registration code map for the given serial number.

    Args:
      serial_number: The DUT's serial number.

    Returns:
      {'user': registration_code, 'group': group_code}
    """
    raise NotImplementedError()

  @RPCCall
  def GetVPD(self, serial_number):
    """Gets VPD data of the DUT.

    Args:
      serial_number: The DUT's serial number.

    Returns:
      VPD data in dict {'ro': dict(), 'rw': dict()}
    """
    raise NotImplementedError()

  @RPCCall
  def CheckSN(self, serial_number):
    """Checks whether a serial number is valid.

    Args:
      serial_number: The DUT's serial number.
    """
    raise NotImplementedError()

  @RPCCall
  def GetMemSize(self, serial_number):
    """Get the memory size of DUT in GB.

    Args:
      serial_number: The DUT's serial number.

    Returns:
      {'mem_size': (float, int)}
    """
    raise NotImplementedError()
