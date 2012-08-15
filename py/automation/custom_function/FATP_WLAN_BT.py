# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

def Main(factory_automation, test_path):  # pylint: disable=W0613
  factory_automation.driver.switch_to_frame(0)
  factory_automation.driver.find_element_by_id('pass').click()
