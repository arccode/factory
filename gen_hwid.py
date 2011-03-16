#!/usr/bin/env python
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This script generates a complete HWID (with checksum) by given arguments.

import sys, zlib
if len(sys.argv) < 2:
  print "Usage: %s HWID_WITHOUT_CHECKSUM" % sys.argv[0]
  sys.exit(1)

me = ' '.join(sys.argv[1:])
print me, ('%04u' % (zlib.crc32(me) & 0xffffffffL))[-4:]
