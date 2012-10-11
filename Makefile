# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SHELL := bash

BUILD_DIR=build
PAR_BUILD_DIR=$(BUILD_DIR)/par
DESTDIR=$(BUILD_DIR)/image
TARGET_DIR=/usr/local/factory
PYTHON_SITEDIR=$(shell echo \
  'from distutils.sysconfig import get_python_lib; ' \
  'print(get_python_lib())' | python)
PYTHON=python

FACTORY=$(DESTDIR)/$(TARGET_DIR)
FACTORY_BUNDLE=$(FACTORY)/bundle

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
	py/test/state_machine.py \
	py/test/state.py \
	py/test/state_unittest.py \
	py/test/task.py \
	py/test/ui.py \
	py/test/unicode_to_string.py \
	py/test/unicode_to_string_unittest.py \
	py/test/utils.py \
	py/test/utils_unittest.py

LINT_FILES=$(shell find py -name '*.py' -type f | sort)
LINT_WHITELIST=$(filter-out $(LINT_BLACKLIST),$(LINT_FILES))

UNITTESTS=$(shell find py -name '*_unittest.py' | sort)
# TODO(sheckylin): Get py/test/media_util_unittest.py working.
UNITTESTS_BLACKLIST=\
	py/test/media_util_unittest.py
UNITTESTS_WHITELIST=$(filter-out $(UNITTESTS_BLACKLIST),$(UNITTESTS))


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
	  --include '*.csv' \
	  --include '*/' --exclude '*' \
	  py/ $(PAR_BUILD_DIR)/cros/factory/
# Copy necessary third-party packages.
	rsync -a \
	  $(PYTHON_SITEDIR)/argparse.py \
	  $(PYTHON_SITEDIR)/jsonrpclib \
	  $(PAR_BUILD_DIR)
# Add empty __init__.py files so Python realizes these directories are
# modules.
	touch $(PAR_BUILD_DIR)/cros/__init__.py
	touch $(PAR_BUILD_DIR)/cros/factory/__init__.py
# Add an empty factory_common file (since many scripts import factory_common).
	touch $(PAR_BUILD_DIR)/factory_common.py
	cd $(PAR_BUILD_DIR) && zip -qr factory.par *
# Sanity check: make sure we can import event_log using only the par file.
	PYTHONPATH=$(PAR_BUILD_DIR)/factory.par $(PYTHON) -c \
	  'import cros.factory.test.state'
	$(if $(PAR_DEST_DIR),cp $(PAR_BUILD_DIR)/factory.par $(PAR_DEST_DIR))

install: par
	mkdir -p $(FACTORY)
	rsync -a --exclude '*.pyc' bin misc py py_pkg sh test_lists $(FACTORY)
	ln -sf bin/gooftool bin/edid bin/hwid_tool ${FACTORY}
	mkdir -m755 -p ${DESTDIR}/var/log
	mkdir -m755 -p $(addprefix ${DESTDIR}/var/factory/,log state tests)
	ln -sf $(addprefix ../factory/log/,factory.log console.log) ${DESTDIR}/var/log
# Make factory bundle overlay
	mkdir -p $(FACTORY_BUNDLE)/shopfloor
	cp -a $(PAR_BUILD_DIR)/factory.par $(FACTORY_BUNDLE)/shopfloor
	cp sh/shopfloor_server.sh $(FACTORY_BUNDLE)/shopfloor

lint:
	@set -e -o pipefail; \
	out=$$(mktemp); \
	echo Linting $(shell echo $(LINT_WHITELIST) | wc -w) files...; \
	if [ -n "$(LINT_WHITELIST)" ] && \
	    ! env PYTHONPATH=py_pkg pylint $(PYLINT_OPTIONS) $(LINT_WHITELIST) \
	    |& tee $$out; then \
	  echo; \
	  echo To re-lint failed files, run:; \
	  echo make lint LINT_WHITELIST=\""$$( \
	    grep '^\*' $$out | cut -c22- | tr . / | \
	    sed 's/$$/.py/' | tr '\n' ' ' | sed -e 's/ $$//')"\"; \
	  echo; \
	  rm -f $$out; \
	  exit 1; \
	fi; \
	echo ...no lint errors! You are awesome!; \
	rm -f $$out

PRESUBMIT_FILES := $(shell echo $$PRESUBMIT_FILES)
PRESUBMIT_FILES := $(patsubst $(shell pwd)/%,%,$(PRESUBMIT_FILES))

lint-presubmit:
	$(MAKE) lint \
	    LINT_FILES="$(filter %.py,$(PRESUBMIT_FILES))" \
	    2>/dev/null

test-presubmit:
	if [ ! -e .tests-passed ]; then \
	    echo 'Unit tests have not passed.  Please run "make test".'; \
	    exit 1; \
	fi
	changed=$$(find $$PRESUBMIT_FILES -newer .tests-passed); \
	if [ -n "$$changed" ]; then \
	    echo "Files have changed since last time unit tests passed:"; \
	    echo "$$changed" | sed -e 's/^/  /'; \
	    echo 'Please run "make test".'; \
	    exit 1; \
	fi

clean:
	rm -rf $(BUILD_DIR)

GREEN=\033[22;32m
RED=\033[22;31m
WHITE=\033[22;0m

test:
	@if ! python -c 'import jsonrpclib'; then \
	    echo '*** jsonrpclib is not available in your chroot. '; \
	    echo '*** Please "sudo emerge dev-python/jsonrpclib".'; \
	    echo '*** (see http://crosbug.com/34858)'; \
	    exit 1; \
	fi
	@total=0; good=0; \
	rm -f .tests-passed; \
	logdir=/tmp/test.logs.$$(date +%Y%m%d_%H%M%S); \
	mkdir $$logdir; \
	echo "Test logs will be written to $$logdir"; \
	echo; \
	for f in $(UNITTESTS_WHITELIST); do \
	    total=$$(expr $$total + 1); \
	    echo -ne "*** RUN $$f"; \
	    log=$$logdir/$$(basename $$f).log; \
	    if $$f >$$log 2>&1; then \
	        good=$$(expr $$good + 1); \
	        echo -e "\r$(GREEN)*** PASS $$f$(WHITE)"; \
	    else \
	        echo -e "\r$(RED)*** FAIL $$f$(WHITE)"; \
	        echo "    (log in $$log)"; \
	        if grep -q "^KeyboardInterrupt" $$log; then \
	            echo "Keyboard interrupt; stopping."; \
	            exit 1; \
	        fi; \
	    fi; \
	done; \
	echo; \
	echo -e "$(GREEN)$$good/$$total tests passed.$(WHITE)"; \
	if [ $$good == $$total ]; then \
	    touch .tests-passed; \
	else \
	    echo -e "$(RED)$$(expr $$total - $$good)/$$total tests failed.$(WHITE)"; \
	    false; \
	fi
