#!/bin/bash
#
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#

# Umpire can serve multiple boards at the same time. Each board uses a different
# set of ports
# 1) base: imaging and shopfloor
# 2) base + 4: rsync
#
# PORT_START specifies the starting port of base port, and PORT_STEP specifies
# the increment to the next set of ports. For example, with NUM_BOARDS=2,
# PORT_START=8080, PORT_STEP=10, the following port will be activated:
#
# 1) 8080, 8084
# 2) 8090, 8094

# Number of boards to support for this container
NUM_BOARDS=3

# Starting base port
PORT_START=8080

# Increament between set of ports
PORT_STEP=10
