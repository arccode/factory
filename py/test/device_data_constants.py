# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from cros.factory.utils import shelve_utils


# Helper utility for manipulating keys.
JoinKeys = shelve_utils.DictKey.Join

# Keys for accessing device data.
KEY_SERIALS = 'serials'
NAME_SERIAL_NUMBER = 'serial_number'
NAME_MLB_SERIAL_NUMBER = 'mlb_serial_number'
KEY_SERIAL_NUMBER = JoinKeys(KEY_SERIALS, NAME_SERIAL_NUMBER)
KEY_MLB_SERIAL_NUMBER = JoinKeys(KEY_SERIALS, NAME_MLB_SERIAL_NUMBER)

KEY_VPD = 'vpd'
NAME_RO = 'ro'
NAME_RW = 'rw'
KEY_VPD_RO = JoinKeys(KEY_VPD, NAME_RO)
KEY_VPD_RW = JoinKeys(KEY_VPD, NAME_RW)

NAME_REGION = 'region'
NAME_USER_REGCODE = 'ubind_attribute'
NAME_GROUP_REGCODE = 'gbind_attribute'
KEY_VPD_REGION = JoinKeys(KEY_VPD_RO, NAME_REGION)
KEY_VPD_USER_REGCODE = JoinKeys(KEY_VPD_RW, NAME_USER_REGCODE)
KEY_VPD_GROUP_REGCODE = JoinKeys(KEY_VPD_RW, NAME_GROUP_REGCODE)

KEY_COMPONENT = 'component'
KEY_COMPONENT_HAS_TOUCHSCREEN = JoinKeys(KEY_COMPONENT, 'has_touchscreen')

KEY_HWID = 'hwid'
KEY_FACTORY = 'factory'

# default key mapping from RO_VPD to device data
DEFAULT_RO_VPD_KEY_MAP = {
    NAME_SERIAL_NUMBER: KEY_SERIAL_NUMBER,
    NAME_MLB_SERIAL_NUMBER: KEY_MLB_SERIAL_NUMBER,
}
# default key mapping from RW_VPD to device data
DEFAULT_RW_VPD_KEY_MAP = {
    'factory.*': KEY_FACTORY
}
