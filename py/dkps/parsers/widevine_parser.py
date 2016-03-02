# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module to parse Widevine keybox XML file content."""

from xml.etree import cElementTree as ET


def Parse(serialized_drm_key_list):
  """Parse the Widevine key XML file content.

  This function turns each Widevine key into a dict that contains the following
  keys:
    - DeviceID
    - Key
    - ID
    - Magix
    - CRC
  Each of the keys above maps to the same name element in Widevine keybox,
  except DeviceID which is an attribute of the keybox.

  Example, a Widevine keybox:

    <Keybox DeviceID="device01">
      <Key>key01</Key>
      <ID>id01</ID>
      <Magic>magic01</Magic>
      <CRC>crc01</CRC>
    </Keybox>

  will be converted into a python dict:

    {'DeviceID': 'device01',
     'Key': 'key01',
     'ID': 'id01',
     'Magic': 'magic01',
     'CRC': 'crc01'},
  """
  widevine_key_list = []

  root = ET.fromstring(serialized_drm_key_list.strip())
  for child in root.iter('Keybox'):
    widevine_key = {'DeviceID': child.attrib['DeviceID'].strip()}
    for key in ['Key', 'ID', 'Magic', 'CRC']:
      widevine_key[key] = child.find(key).text
    widevine_key_list.append(widevine_key)

  return widevine_key_list
