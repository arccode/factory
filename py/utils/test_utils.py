# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''Test-related utilities...'''


import random


def FindUnusedTCPPort():
    '''Returns an unused TCP port for testing.

    Currently just returns a random port from [10000,20000).
    '''
    return random.randint(10000, 19999)
