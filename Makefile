# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

BUILD_DIR=build
DESTDIR=$(BUILD_DIR)/image
TARGET_DIR=/usr/local/factory

FACTORY=$(DESTDIR)/$(TARGET_DIR)

PYLINTRC=../../../chromite/pylintrc

PYLINT_OPTIONS=\
	--rcfile=$(PYLINTRC) \
	--ignored-classes=Event,Obj \
	--disable=R0921 \
	--generated-members=test_info,AndReturn,AndRaise

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

# Temporary changes for broken code.  TODO(tammo, itspeter): Remove.
LINT_BLACKLIST += \
	py/gooftool/gooftool.py \
	py/hwdb/hwid_tool.py \
	py/test/pytests/probe_cellular_info.py

LINT_FILES=$(filter-out $(LINT_BLACKLIST), \
               $(shell find py -name '*.py' -type f | sort))

UNITTESTS=\
	py/event_log_unittest.py \
	py/goofy/charge_manager_unittest.py \
	py/goofy/event_log_watcher_unittest.py \
	py/goofy/goofy_rpc_unittest.py \
	py/goofy/goofy_unittest.py \
	py/goofy/system_unittest.py \
	py/goofy/time_sanitizer_unittest.py \
	py/goofy/updater_unittest.py \
	py/test/factory_unittest.py \
	py/test/state_unittest.py \
	py/test/unicode_to_string_unittest.py \
	py/test/utils_unittest.py \
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

install:
	mkdir -p $(FACTORY)
	cp -ar bin misc py py_pkg sh test_lists $(FACTORY)
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
