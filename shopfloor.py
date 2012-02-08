# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


"""Wrapper for Factory Shopfloor.

See the detail protocols in factory-utils/factory_setup/shopfloor_server.
"""


import xmlrpclib

# Key names for factory state shared data
KEY_ENABLED = "shopfloor.enabled"
KEY_SERVER_URL = "shopfloor.server_url"
KEY_SERIAL_NUMBER = "shopfloor.serial_number"

# Default port number from shopfloor_server.py.
_DEFAULT_SERVER_PORT = 8082


def get_instance(address, port=_DEFAULT_SERVER_PORT):
    '''
    Gets an instance (for client side) to access the shop floor server.

    @param address: Address of the server to be connected.
    @param port: Port of the server to be connected.
    @return An object with all public functions from shopfloor.ShopFloorBase.
    '''
    return xmlrpclib.ServerProxy('http://%s:%d' % (address, port),
                                 allow_none=True, verbose=False)


def check_server_status(instance):
    '''
    Checks if the given instance is successfully connected.
    @param instance: Instance object created get_instance.
    @return True for success, otherwise raise exception.
    '''
    try:
        instance.proxy.system.listMethods()
    except:
        raise
    return True
