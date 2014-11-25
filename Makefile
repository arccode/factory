# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SHELL := bash

BUILD_DIR=build
PAR_BUILD_DIR=$(BUILD_DIR)/par
PAR_NAME=factory.par
DESTDIR=$(BUILD_DIR)/image
TARGET_DIR=/usr/local/factory
PYTHON=python

# The list of binaries to install has been moved to misc/symlinks.yaml.

TEST_RUNNER=py/tools/run_tests.py
# Maximum number of parallel tests to run.
MAX_TESTS=$(shell grep -c ^processor /proc/cpuinfo)

FACTORY=$(DESTDIR)/$(TARGET_DIR)
FACTORY_BUNDLE=$(FACTORY)/bundle

PYLINTRC=pylintrc

# Extra arguments to give to the make_par command (e.g., to add
# files from overlays).
MAKE_PAR_ARGS=

# TODO(shik): Re-enable R0801 once flash_firmware.py and
# setup_netboot.py are fixed.
PYLINT_OPTIONS=--rcfile=$(PYLINTRC)

LINT_BLACKLIST=\
	py/argparse.py \
	py/gooftool/vblock.py \
	py/goofy/invocation.py \
	py/goofy/prespawner.py \
	py/goofy/test_environment.py \
	py/goofy/updater.py \
	py/goofy/web_socket_manager.py \
	py/hwdb/convert_to_v2_test_files/components_SAMS_TEST-ALFA_1111 \
	py/hwdb/convert_to_v2_test_files/components_SAMS_TEST-BETA_2222 \
	py/hwdb/convert_to_v2_test_files/components_SAMS_TEST-CHARLIE_3333 \
	py/hwdb/convert_to_v2_test_files/components_SAMS_TEST-DELTA_4444 \
	py/hwdb/convert_to_v2_test_files/v15_TEST_FILE \
	py/shopfloor/shopfloor_standalone_unittest.py \
	py/shopfloor/template.py \
	py/system/charge_manager_unittest.py \
	py/test/event.py \
	py/test/gooftools.py \
	py/test/leds.py \
	py/test/line_item_check.py \
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
	py/test/utils_unittest.py \
	py/test/fixture/camera/grid_mapper.py \
	py/minijack/apiclient/% \
	py/minijack/gflags.py \
	py/minijack/gflags_validators.py \
	py/minijack/httplib2/% \
	py/minijack/oauth2client/% \
	py/minijack/uritemplate/% \
	py/proto/%_pb2.py

LINT_FILES=$(shell find py -name '*.py' -type f | sort)
LINT_WHITELIST=$(filter-out $(LINT_BLACKLIST),$(LINT_FILES))

UNITTESTS=$(shell find py -name '*_unittest.py' | sort)
# TODO(sheckylin): Get py/test/media_util_unittest.py working.
UNITTESTS_BLACKLIST=\
	py/test/media_util_unittest.py
UNITTESTS_WHITELIST=$(filter-out $(UNITTESTS_BLACKLIST),$(UNITTESTS))
# Tests need to run in isolate mode.
UNITTESTS_ISOLATE_LIST=\
       py/goofy_split/goofy_unittest.py \
       py/goofy_split/system_log_manager_unittest.py

INSTALL_MASK=*.pyc \
	     *_unittest.py \
	     py/doc


# TODO(jsalz): remove the hard-coded path once the icedtea6-bin
# package is fixed and /usr/bin/java works
# (https://bugs.gentoo.org/416341)
default:
	for goofy_path in py/goofy_monolithic/static py/goofy_split/static; do\
	    env PATH=/opt/icedtea6-bin-1.6.2/bin:$(PATH) \
	        $(MAKE) -C "$${goofy_path}" \
	          $(if $(CLOSURE_LIB_DIR), \
	                CLOSURE_LIB_DIR="$(CLOSURE_LIB_DIR)",) ; \
	done


# Build par (Python archive) file containing all py and pyc files.
par:
	rm -rf $(PAR_BUILD_DIR)
	mkdir -p $(PAR_BUILD_DIR)
	# First build factory.par.
	bin/make_par -v \
	  -o $(PAR_BUILD_DIR)/$(PAR_NAME) \
	  $(MAKE_PAR_ARGS)
	# Sanity check: make sure we can import state using only
	# factory.par.
	PYTHONPATH=$(PAR_BUILD_DIR)/$(PAR_NAME) $(PYTHON) -c \
	  'import cros.factory.test.state'; \
	# Sanity check: make sure we can run "gooftool --help" using
	# factory.par.
	$(PAR_BUILD_DIR)/$(PAR_NAME) gooftool --help | \
	  grep -q '^usage: gooftool'
	$(if $(PAR_DEST_DIR), \
	  cp $(PAR_BUILD_DIR)/$(PAR_NAME) \
	  $(PAR_DEST_DIR))

install:
	mkdir -p $(FACTORY)
	rsync -a --chmod=go=rX $(addprefix --exclude ,$(INSTALL_MASK)) \
	  bin misc py py_pkg sh init $(FACTORY)
	ln -sf bin/gooftool bin/edid bin/hwid_tool ${FACTORY}
	mkdir -m755 -p ${DESTDIR}/var/log
	mkdir -m755 -p $(addprefix ${DESTDIR}/var/factory/,log state tests)
	ln -sf $(addprefix ../factory/log/,factory.log console.log) \
	    ${DESTDIR}/var/log

bundle: par
	# Make factory bundle overlay
	mkdir -p $(FACTORY_BUNDLE)/factory_setup/
	rsync -a --exclude testdata --exclude README.txt \
	  setup/ $(FACTORY_BUNDLE)/factory_setup/
	mkdir -p $(FACTORY_BUNDLE)/shopfloor
	cp -a $(PAR_BUILD_DIR)/$(PAR_NAME) \
	  $(FACTORY_BUNDLE)/shopfloor
	ln -s $(PAR_NAME) $(FACTORY_BUNDLE)/shopfloor/shopfloor_server
	ln -s $(PAR_NAME) $(FACTORY_BUNDLE)/shopfloor/manage
	ln -s $(PAR_NAME) $(FACTORY_BUNDLE)/shopfloor/minijack
	ln -s $(PAR_NAME) $(FACTORY_BUNDLE)/shopfloor/shopfloor
	mkdir -p $(FACTORY_BUNDLE)/factory_flow
	# Create a dedicated directory for factory flow tools.
	cp -a $(PAR_BUILD_DIR)/$(PAR_NAME) $(FACTORY_BUNDLE)/factory_flow
	ln -s $(PAR_NAME) $(FACTORY_BUNDLE)/factory_flow/factory_flow
	ln -s $(PAR_NAME) $(FACTORY_BUNDLE)/factory_flow/finalize_bundle
	ln -s $(PAR_NAME) $(FACTORY_BUNDLE)/factory_flow/test_factory_flow
	# Archive docs into bundle
	$(MAKE) doc
	cp build/doc.tar.bz2 $(FACTORY_BUNDLE)
	# Install cgpt, used by factory_setup.
	# TODO(jsalz/hungte): Find a better way to do this.
	mkdir -p $(FACTORY_BUNDLE)/factory_setup/bin
	cp /usr/bin/cgpt $(FACTORY_BUNDLE)/factory_setup/bin
	cp /usr/bin/futility $(FACTORY_BUNDLE)/factory_setup/bin

lint:
	@set -e -o pipefail; \
	out=$$(mktemp); \
	echo Linting $(shell echo $(LINT_WHITELIST) | wc -w) files...; \
	if [ -n "$(LINT_WHITELIST)" ] && \
			! env PYTHONPATH=py_pkg:py/minijack:setup \
			pylint $(PYLINT_OPTIONS) $(LINT_WHITELIST) \
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

# Target to lint only files that have changed.  (We allow either
# "smartlint" or "smart_lint".)
smartlint smart_lint:
	bin/smart_lint

# Substitute PRESUBMIT_FILES to relative path (similar to
# GNU realpath "--relative-to=.", but works on non-GNU realpath).
PRESUBMIT_FILES := $(if $(PRESUBMIT_FILES), \
	             $(shell realpath $$PRESUBMIT_FILES | \
		       sed "s'^$$(realpath $$(pwd))/''g"))

chroot-presubmit:
	$(MAKE) -s deps-presubmit
	$(MAKE) -s lint-presubmit
	$(MAKE) -s test-presubmit
	$(MAKE) -s make-factory-package-presubmit

lint-presubmit:
	$(MAKE) lint \
	    LINT_FILES="$(filter %.py,$(PRESUBMIT_FILES))" \
	    2>/dev/null

deps-presubmit:
	@echo "Checking dependency..."
	@if ! py/tools/deps.py $(PRESUBMIT_FILES) ; then \
	    echo "Dependency check failed." ; \
	    echo "Please read py/tools/deps.conf for more information." ; \
	    exit 1; \
	fi

# Check that test_make_factory_package.py has been run, if
# make_factory_package.sh has changed.
make-factory-package-presubmit:
	if [ "$(filter setup/make_factory_package.sh,$(PRESUBMIT_FILES))" ]; \
	then \
	  if [ ! setup/make_factory_package.sh -ot \
	       py/tools/.test_make_factory_package.passed ]; then \
	    echo setup/make_factory_package.sh has changed.; \
	    echo Please run py/tools/test_make_factory_package.py; \
	    echo \(use --help for more information on how to use it if; \
	    echo you do not have access to release repositories\).; \
	    exit 1; \
	  fi; \
	fi

test-presubmit:
	if [ ! -e .tests-passed ]; then \
	    echo 'Unit tests have not passed.  Please run "make test".'; \
	    exit 1; \
	fi
	changed=$$(find $(filter-out doc/%,$(PRESUBMIT_FILES)) \
	    -newer .tests-passed); \
	if [ -n "$$changed" ]; then \
	    echo "Files have changed since last time unit tests passed:"; \
	    echo "$$changed" | sed -e 's/^/  /'; \
	    echo 'Please run "make test" inside chroot.'; \
	    exit 1; \
	fi

presubmit:
	@if [ ! -e /etc/debian_chroot ]; then \
		echo "Running presubmit checks inside chroot..."; \
		cros_sdk PRESUBMIT_FILES="$(PRESUBMIT_FILES)" -- \
		make -C ../platform/factory -s chroot-presubmit; \
	else \
		$(MAKE) -s chroot-presubmit; \
	fi

clean:
	rm -rf $(BUILD_DIR)

test:
        # Run tests with POSIX locale to avoid localized output.
	find . -name '*.pyc' -delete
	@logdir=/tmp/test.logs.$$(date +%Y%m%d_%H%M%S); \
	mkdir $$logdir; \
	echo "Test logs will be written to $$logdir"; \
	test -d "$(CURDIR)/../../private-overlays" \
	    || echo "$$(tput setaf 1)Warning: Private components are missing."\
	            "Some tests are likely to fail without them.$$(tput sgr0)";\
	echo; \
	LC_ALL="C" $(TEST_RUNNER) $(UNITTESTS_WHITELIST) -i $(UNITTESTS_ISOLATE_LIST) \
            -j $(MAX_TESTS) -l $$logdir $(EXTRA_TEST_FLAGS)

# Trick to make sure that overlays are rebuilt every time overlay-xxx is run.
.PHONY: .phony

# Builds an overlay of the given board.  Use "private" to overlay
# factory-private (e.g., to build private API docs).
overlay-%: .phony
	rm -rf $@
	mkdir $@
	rsync -aK --exclude build --exclude overlay-\* ./ $@/
	if [ "$@" = overlay-private ]; then \
	  rsync -aK --exclude Makefile ../factory-private/ $@/; \
	else \
	  rsync -aK ../../private-overlays/\
overlay*-$(subst overlay-,,$@)-private/chromeos-base/chromeos-factory-board/\
files/ $@/; \
	fi

# Tests the overlay of the given board.
test-overlay-%: overlay-%
	make -C $< test && touch .tests-passed

# Lints the overlay of the given board.
lint-overlay-%: overlay-%
	make -C $< lint

testall:
	@make --no-print-directory test EXTRA_TEST_FLAGS=--nofilter

# Regenerates the reg code proto.  TODO(jsalz): Integrate this as a
# "real" part of the build, rather than relying on regenerating it
# only if/when it changes.  This is OK for now since this proto should
# change infrequently or never.
proto:
	protoc proto/reg_code.proto --python_out=py

# Creates build/doc and build/doc.tar.bz2, containing the factory SDK
# docs.
doc: .phony
	# Do the actual build in the "build/docsrc" directory, since we need to
	# munge the docs a bit.
	rm -rf $(BUILD_DIR)/docsrc
	mkdir -p $(BUILD_DIR)/docsrc
	rsync -av doc/ $(BUILD_DIR)/docsrc/
	# Generate rst sources for test cases
	bin/generate_rsts -o $(BUILD_DIR)/docsrc

	make -C $(BUILD_DIR)/docsrc html
	rm -rf $(BUILD_DIR)/doc
	mkdir -p $(BUILD_DIR)/doc
	rsync -a $(BUILD_DIR)/docsrc/_build/ $(BUILD_DIR)/doc/
	cd $(BUILD_DIR) && tar cfj doc.tar.bz2 doc
