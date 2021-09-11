# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# This module defined all allowed VPD entry and format.


"""Collection of valid VPD values for Chrome OS."""


# Shortcut to allow arbitrary format.
ANY = r'.+'
ANY_OR_EMPTY = r'.*'

# The data is described in a mapping as key_name: value_re_format.
# Note value_re_format has implicit '^' and '$' (see MatchWhole in core.py).
# so when you write r'[A-Z]' it will be evaluated as r'^[A-Z]$'.

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

# KNOWN = Recommended + Optional, and "required but is auto generated".
KNOWN_RO_DATA = {
    # Generated in finalization.
    'stable_device_secret_DO_NOT_SHARE': ANY,
    'mfg_date': r'\d{4}-\d{2}-\d{2}',  # yyyy-mm-dd

    # Optional values.
    'mlb_serial_number': ANY,
    'whitelabel_tag': ANY_OR_EMPTY,
    'System_UUID': ANY,
    'sku_number': ANY,
    'model_name': ANY,
    'service_tag': ANY,
    'dsm_calib': r'[0-9a-f ]*',
    'oem_device_requisition': ANY,
    'attested_device_id': ANY,
    # See util/vpd_icc in https://crrev.com/c/2058225
    'display_profiles': r'[0-9a-fA-F]{8}:.+',
}

# Variable key names in regular expression.
KNOWN_RO_DATA_RE = {
    # Recommended values.
    r'(ethernet|wifi|bluetooth|zigbee)_mac[0-9]+': r'[0-9a-fA-F:]+',
    r'(ethernet|wifi|bluetooth|zigbee)_calibration[0-9]*': ANY,
    r'in_(accel|anglvel)_(x|y|z)_(base|lid)_calib(bias|scale)': r'-*[0-9]+',
    r'als_cal_(slope|slope_color|intercept)': ANY,
    r'dsm_calib_r0_[0-9]+': r'[0-9]*',
    r'dsm_calib_temp_[0-9]+': r'[0-9]*',
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
    'enterprise_management_embargo_end_date': r'\d{4}-\d{2}-\d{2}',
}

KNOWN_RW_DATA_RE = {
    # These VPD values are used only for factory process and should be deleted
    # by "gooftool clear_factory_vpd_entries" in finalization.
    r'factory\..+': ANY,
    r'component\..+': ANY,
    r'serials\..+': ANY,
}

# These values are deprecated and simply put here as reference. To allow them
# in particular factory branch, please first get approval from Google team.
DEPRECATED_RO_DATA = {
    'initial_locale': ANY,
    'initial_timezone': ANY,
    'keyboard_layout': ANY,
    'rlz_brand_code': r'[A-Z]{4}',
    'customization_id': r'[A-Z0-9]+(-[A-Z0-9]+)?',
    'battery_cto_disabled': ANY,
    'panel_backlight_max_nits': r'[0-9]+',  # See b/110185527.
    # This is moved to CBFS, please check with RF eng if this really needs to be
    # added to your project.
    r'wifi_sar[0-9]*': ANY,
}
