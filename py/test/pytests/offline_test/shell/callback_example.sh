#!/bin/sh
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# this file is an example of callback functions for shell offline test.
# the purpose is these functions are to nofity operators. For example, set LED
# to green if all tests are passed, set LED to blue if the test is still running
# and set LED to red if tests failed.

on_all_test_passed() {
  # this function is called when all tests are passed.
  ectool led power green
}

on_test_failed() {
  # this function is called when a test fails.
  ectool led power red
}

on_start_test() {
  # this function is called when a test starts.
  ectool led power blue
}
