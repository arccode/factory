# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

DESTDIR=image
TARGET_DIR=/usr/local/factory

FACTORY=${DESTDIR}/${TARGET_DIR}

# TODO(jsalz): remove the hard-coded path once the icedtea6-bin
# package is fixed and /usr/bin/java works
# (https://bugs.gentoo.org/416341)
default:
	env PATH=/opt/icedtea6-bin-1.6.2/bin:${PATH} \
	    $(MAKE) -C py/goofy/static \
	        CLOSURE_LIB_ARCHIVE="${CLOSURE_LIB_ARCHIVE}"

install:
	mkdir -p ${FACTORY}
	cp -ar bin misc py py_pkg sh test_lists ${FACTORY}
	ln -s bin/gooftool bin/edid bin/hwid_tool ${FACTORY}
