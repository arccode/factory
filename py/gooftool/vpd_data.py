# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# This module defined all allowed VPD entry and format.


"""Collection of valid VPD values for Chrome OS."""


# Shortcut to allow arbitrary format.
ANY = r'.+'

# The data is described in a mapping as key_name: value_re_format.
# All values should be documented in CPFE:
#  https://www.google.com/chromeos/partner/fe/docs/factory/vpd.html .
# If you need a new value, please follow go/cros-new-vpd to register a new one.

REQUIRED_RO_DATA = {
    'serial_number': ANY,
    'region': ANY,  # Or regions.REGIONS.iterkeys
}

REQUIRED_RW_DATA = {
    'ubind_attribute': ANY,
    'gbind_attribute': ANY,
}

KNOWN_RO_DATA = {
    # Generated in finalization.
    'stable_device_secret_DO_NOT_SHARE': ANY,

    # Optional values.
    'mlb_serial_number': ANY,
    'whitelabel_tag': ANY,
    'System_UUID': ANY,
    'sku_number': ANY,
    'model_name': ANY,
    'service_tag': ANY,
    'panel_backlight_max_nits': ANY,
    'dsm_calib': r'^[0-9a-f ]*$',
}

# Variable key names in regular expression.
KNOWN_RO_DATA_RE = {
    # Recommended values.
    r'(ethernet|wifi|bluetooth|zigbee)_mac[0-9]*': r'[0-9a-fA-F:]+',
    r'(ethernet|wifi|bluetooth|zigbee)_calibration[0-9]*': ANY,
    r'wifi_sar[0-9]*': ANY,
    r'in_(accel|anglvel)_(x|y|z)_(base|lid)_calib(bias|scale)': r'-*[0-9]+',
    r'als_cal_(slope|intercept)': ANY,
}

KNOWN_RW_DATA = {
    # These VPD values will be generated later but should not exist when leaving
    # factory (but some may exist in RMA process).
    'ActivateDate': ANY,
    'block_devmode': ANY,
    'check_enrollment': ANY,
    'first_active_omaha_ping_sent': ANY,
    'tpm_firmware_update_params': ANY,

    # In factory, a new device should have should_send_rlz_ping='1'.
    # In RMA center, this value might be '0'.
    # If they replace a new MLB in RMA center, then these fields will not exist.
    'should_send_rlz_ping': r'[01]',
    'rlz_embargo_end_date': r'\d{4}-\d{2}-\d{2}',  # yyyy-mm-dd
}

KNOWN_RW_DATA_RE = {
    # These VPD values are used only for factory process and should be deleted
    # by "gooftool clear_factory_vpd_entries" in finalization.
    r'factory\..+': ANY,
    r'component\..+': ANY,
    r'serials\..+': ANY,
}
