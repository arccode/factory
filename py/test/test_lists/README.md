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
Normally, the ID of the active test list is stored in
`/usr/local/factory/py/config/active_test_list.json` just like other build time
configurations.  Goofy first tries to read the ID of the active test list
from that config file.  And the command `factory test-list <test-list-id>`
stores the specified test list ID to that file.

If no active test list configuration is present, then there are two ways to
determine the default test list:

1. ID - `main_${model}` would be checked first where `${model}` is came from
output of command - `cros_config / name`.
2. the test list with ID - `main` or `generic_main` is used.

### Override the Active Test List
`setup/cros_docker.sh goofy try` allows developers to run the factory software
from source locally.  In this usecase, we suggest the developers to manually
save the active test list ID to `/var/factory/config/active_test_list.json`
in the docker because having `py/config/active_test_list.json` on the
developer's computer makes it easy to build a toolkit with unexpected default
active test list.

Please note that `factory test-list <test-list-id>` command will become not
working when `/var/factory/config/active_test_list.json` is set.  The reason
is that Goofy will always try to get the ID from the configuration under `/var`
first but `factory test-list <test-list-id>` command will still save the
ID to `/usr/local/factory/py/config/active_test_list.json`.
