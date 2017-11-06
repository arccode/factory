<!--
 # Copyright 2017 The Chromium OS Authors. All rights reserved.
 # Use of this source code is governed by a BSD-style license that can be
 # found in the LICENSE file.
 -->

ChromeOS Factory Test Lists
===========================
This package contains factory test lists.
See: [http://goto/cros-factory-test-list](http://goto/cros-factory-test-list)
or [JSON_TEST_LIST.md](./JSON_TEST_LIST.md)

TEST LISTS
----------
On startup, test list `manager` loads all `*.test_list.json` in this directory.
If the JSON file defines `tests`, the test list ID will be exported as a valid
test list.  Use command `factory test-list --list` to find all valid test lists,
and `factory test-list <test-list-id>` to activate the test list.

THE ACTIVE TEST LIST
--------------------
If a file called `ACTIVE` is present in this directory, it contains the
ID of the active test list.  So, for example, to activate the `generic_main`
test list on a device:

    echo generic_main > /usr/local/factory/py/test/test_lists/ACTIVE

If no `ACTIVE` file is present, the `main` test list is used.

(Note that `ACTIVE` is a file, not a symlink to a file as in the past.)
