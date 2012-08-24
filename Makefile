# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

BUILD_DIR=build
PAR_BUILD_DIR=$(BUILD_DIR)/par
DESTDIR=$(BUILD_DIR)/image
TARGET_DIR=/usr/local/factory
PYTHON_SITEDIR=$(shell echo \
  'from distutils.sysconfig import get_python_lib; ' \
  'print(get_python_lib())' | python)
PYTHON=python

FACTORY=$(DESTDIR)/$(TARGET_DIR)
PAR_DEST_DIR=$(FACTORY)

PYLINTRC=../../../chromite/pylintrc

# TODO(shik): Re-enable R0801 once flash_firmware.py and
# setup_netboot.py are fixed.
PYLINT_OPTIONS=\
	--rcfile=$(PYLINTRC) \
	--ignored-classes=Event,Obj \
	--disable=R0921,R0801 \
	--generated-members=test_info,AndReturn,AndRaise,args

LINT_BLACKLIST=\
	py/argparse.py \
	py/gooftool/vblock.py \
	py/goofy/invocation.py \
	py/goofy/connection_manager.py \
	py/goofy/event_log_watcher.py \
	py/goofy/event_log_watcher_unittest.py \
	py/goofy/prespawner.py \
	py/goofy/test_environment.py \
	py/goofy/updater.py \
	py/goofy/web_socket_manager.py \
	py/shopfloor/__init__.py \
	py/shopfloor/factory_update_server.py \
	py/shopfloor/factory_update_server_unittest.py \
	py/shopfloor/shopfloor_server.py \
	py/shopfloor/shopfloor_standalone_unittest.py \
	py/shopfloor/template.py \
	py/system/charge_manager_unittest.py \
	py/test/event.py \
	py/test/gooftools.py \
	py/test/leds.py \
	py/test/line_item_check.py \
	py/test/media_util.py \
	py/test/media_util_unittest.py \
	py/test/pytests/execpython.py \
	py/test/shopfloor.py \
	py/test/state_machine.py \
	py/test/state.py \
	py/test/state_unittest.py \
	py/test/task.py \
	py/test/ui.py \
	py/test/unicode_to_string.py \
	py/test/unicode_to_string_unittest.py \
	py/test/utils.py \
	py/test/utils_unittest.py

# Temporary changes for broken code.  TODO(jsalz, itspeter): Remove.
LINT_BLACKLIST += \
	py/test/pytests/probe_cellular_info.py \
	py/goofy/goofy.py

LINT_FILES=$(filter-out $(LINT_BLACKLIST), \
               $(shell find py -name '*.py' -type f | sort))

UNITTESTS=\
	py/board/chromeos_ec_unittest.py \
	py/event_log_unittest.py \
	py/goofy/event_log_watcher_unittest.py \
	py/goofy/goofy_rpc_unittest.py \
	py/goofy/goofy_unittest.py \
	py/goofy/time_sanitizer_unittest.py \
	py/goofy/updater_unittest.py \
	py/shopfloor/factory_update_server_unittest.py \
	py/shopfloor/shopfloor_unittest.py \
	py/shopfloor/shopfloor_standalone_unittest.py \
	py/system/charge_manager_unittest.py \
	py/system/system_unittest.py \
	py/test/factory_unittest.py \
	py/test/state_unittest.py \
	py/test/registration_codes_unittest.py \
	py/test/unicode_to_string_unittest.py \
	py/test/utils_unittest.py \
	py/tools/diff_image_unittest.py \
	py/utils/net_utils_unittest.py \
	py/utils/process_utils_unittest.py \
	py/hwdb/hwid_unittest.py

# TODO(sheckylin): Get py/test/media_util_unittest.py working.

# TODO(jsalz): remove the hard-coded path once the icedtea6-bin
# package is fixed and /usr/bin/java works
# (https://bugs.gentoo.org/416341)
default:
	env PATH=/opt/icedtea6-bin-1.6.2/bin:$(PATH) \
	    $(MAKE) -C py/goofy/static \
	        $(if $(CLOSURE_LIB_ARCHIVE), \
                  CLOSURE_LIB_ARCHIVE="$(CLOSURE_LIB_ARCHIVE)",)

par:
# Build par (Python archive) file containing all py and pyc files.
	rm -rf $(PAR_BUILD_DIR)
	mkdir -p $(PAR_BUILD_DIR)/cros
	rsync -a \
	  --exclude '*_unittest.py' \
	  --exclude 'factory_common.py*' \
	  --include '*.py' \
	  --include '*/' --exclude '*' \
	  py/ $(PAR_BUILD_DIR)/cros/factory/
# Copy necessary third-party packages.
	rsync -a $(PYTHON_SITEDIR)/jsonrpclib $(PAR_BUILD_DIR)
# Add empty __init__.py files so Python realizes these directories are
# modules.
	touch $(PAR_BUILD_DIR)/cros/__init__.py
	touch $(PAR_BUILD_DIR)/cros/factory/__init__.py
# Add an empty factory_common file (since many scripts import factory_common).
	touch $(PAR_BUILD_DIR)/factory_common.py
	cd $(PAR_BUILD_DIR) && zip -qr factory.par *
	mv $(PAR_BUILD_DIR)/factory.par $(PAR_DEST_DIR)
# Sanity check: make sure we can import event_log using only the par file.
	PYTHONPATH=$(FACTORY)/factory.par $(PYTHON) -c \
	  'import cros.factory.test.state'

install:
	mkdir -p $(FACTORY)
	rsync -a --exclude '*.pyc' bin misc py py_pkg sh test_lists $(FACTORY)
	ln -sf bin/gooftool bin/edid bin/hwid_tool ${FACTORY}
	mkdir -m755 -p ${DESTDIR}/var/log
	mkdir -m755 -p $(addprefix ${DESTDIR}/var/factory/,log state tests)
	ln -sf $(addprefix ../factory/log/,factory.log console.log) ${DESTDIR}/var/log


lint:
	env PYTHONPATH=py_pkg pylint $(PYLINT_OPTIONS) $(LINT_FILES)

clean:
	rm -rf $(BUILD_DIR)

GREEN=\033[22;32m
RED=\033[22;31m
WHITE=\033[22;0m

test:
	@total=0; good=0; \
	logdir=/tmp/test.logs.$$(date +%Y%m%d_%H%M%S); \
	mkdir $$logdir; \
	echo "Test logs will be written to $$logdir"; \
	echo; \
	for f in $(UNITTESTS); do \
	    total=$$(expr $$total + 1); \
	    echo -ne "*** RUN $$f"; \
	    log=$$logdir/$$(basename $$f).log; \
	    if $$f >$$log 2>&1; then \
	        good=$$(expr $$good + 1); \
	        echo -e "\r$(GREEN)*** PASS $$f$(WHITE)"; \
	    else \
	        echo -e "\r$(RED)*** FAIL $$f$(WHITE)"; \
	        echo "    (log in $$log)"; \
	    fi; \
	done; \
	echo; \
	echo -e "$(GREEN)$$good/$$total tests passed.$(WHITE)"; \
	if [ $$good != $$total ]; then \
	    echo -e "$(RED)$$(expr $$total - $$good)/$$total tests failed.$(WHITE)"; \
	    false; \
	fi
