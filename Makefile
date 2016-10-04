# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SHELL := bash

MK_DIR=mk
BUILD_DIR=$(CURDIR)/build
PAR_BUILD_DIR=$(BUILD_DIR)/par
PAR_NAME=factory.par
DESTDIR=$(BUILD_DIR)/image
TARGET_DIR=/usr/local/factory
PYTHON=python

# The list of binaries to install has been moved to misc/symlinks.yaml.

FACTORY=$(DESTDIR)/$(TARGET_DIR)
FACTORY_BUNDLE=$(FACTORY)/bundle

# Extra arguments to give to the make_par command (e.g., to add
# files from overlays).
MAKE_PAR_ARGS=

LINT_BLACKLIST=$(shell cat $(MK_DIR)/pylint.blacklist)
LINT_FILES=$(shell find py go -name '*.py' -type f | sort)
LINT_WHITELIST=$(filter-out $(LINT_BLACKLIST),$(LINT_FILES))

UNITTESTS=$(shell find py go -name '*_unittest.py' | sort)
UNITTESTS_BLACKLIST=$(shell cat $(MK_DIR)/unittests.blacklist)
UNITTESTS_WHITELIST=$(filter-out $(UNITTESTS_BLACKLIST),$(UNITTESTS))
TEST_EXTRA_FLAGS=

INSTALL_MASK=*.pyc \
	     *_unittest.py \
	     py/doc


default:
	$(MAKE) -C py/goofy/static


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
	ln -sf $(PAR_NAME) $(FACTORY_BUNDLE)/shopfloor/shopfloor_server
	ln -sf $(PAR_NAME) $(FACTORY_BUNDLE)/shopfloor/manage
	ln -sf $(PAR_NAME) $(FACTORY_BUNDLE)/shopfloor/minijack
	ln -sf $(PAR_NAME) $(FACTORY_BUNDLE)/shopfloor/shopfloor
	mkdir -p $(FACTORY_BUNDLE)/factory_flow
	# Create a dedicated directory for factory flow tools.
	cp -a $(PAR_BUILD_DIR)/$(PAR_NAME) $(FACTORY_BUNDLE)/factory_flow
	ln -sf $(PAR_NAME) $(FACTORY_BUNDLE)/factory_flow/factory_flow
	ln -sf $(PAR_NAME) $(FACTORY_BUNDLE)/factory_flow/finalize_bundle
	ln -sf $(PAR_NAME) $(FACTORY_BUNDLE)/factory_flow/test_factory_flow
	# Archive docs into bundle
	$(MAKE) doc
	cp build/doc.tar.bz2 $(FACTORY_BUNDLE)
	# Install cgpt, used by factory_setup.
	# TODO(jsalz/hungte): Find a better way to do this.
	mkdir -p $(FACTORY_BUNDLE)/factory_setup/bin
	cp /usr/bin/cgpt $(FACTORY_BUNDLE)/factory_setup/bin
	cp /usr/bin/futility $(FACTORY_BUNDLE)/factory_setup/bin

lint:
	$(MK_DIR)/pylint.sh $(LINT_WHITELIST)

# Target to lint only files that have changed.  (We allow either
# "smartlint" or "smart_lint".)
smartlint smart_lint:
	bin/smart_lint

# Target to lint only files that have changed, including files from
# the given overlay.
smart_lint-%:
	bin/smart_lint --overlay $(@:smart_lint-%=%)

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
	$(MAKE) lint LINT_FILES="$(filter %.py,$(PRESUBMIT_FILES))" 2>/dev/null

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
	$(MK_DIR)/test-presubmit.sh $(PRESUBMIT_FILES)

presubmit:
	@if [ ! -e /etc/debian_chroot ]; then \
		echo "Running presubmit checks inside chroot..."; \
		cros_sdk PRESUBMIT_FILES="$(PRESUBMIT_FILES)" -- \
		$(MAKE) -C ../platform/factory -s chroot-presubmit; \
	else \
		$(MAKE) -s chroot-presubmit; \
	fi

clean:
	rm -rf $(BUILD_DIR)

test:
	@TEST_EXTRA_FLAGS=$(TEST_EXTRA_FLAGS) \
		$(MK_DIR)/test.sh $(UNITTESTS_WHITELIST)

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
	  rsync -aK "$(shell dirname $(shell equery-$(subst overlay-,,$@) \
	               which chromeos-factory-board))/files/" $@/; \
	fi

# Tests the overlay of the given board.
test-overlay-%: overlay-%
	$(MAKE) -C $< test && touch .tests-passed

# Lints the overlay of the given board.
lint-overlay-%: overlay-%
	$(MAKE) -C $< lint

# Create par of the given board.
par-overlay-%: overlay-%
	$(MAKE) -C $< par

testall:
	@$(MAKE) --no-print-directory test TEST_EXTRA_FLAGS=--nofilter

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

	$(MAKE) -C $(BUILD_DIR)/docsrc html
	rm -rf $(BUILD_DIR)/doc
	mkdir -p $(BUILD_DIR)/doc
	rsync -a $(BUILD_DIR)/docsrc/_build/ $(BUILD_DIR)/doc/
	cd $(BUILD_DIR) && tar cfj doc.tar.bz2 doc

ovl-bin:
	# Create virtualenv environment
	rm -rf $(BUILD_DIR)/.env
	virtualenv $(BUILD_DIR)/.env
	# Build ovl binary with pyinstaller
	cd $(BUILD_DIR); \
	source $(BUILD_DIR)/.env/bin/activate; \
	pip install jsonrpclib ws4py pyinstaller; \
	pyinstaller --onefile $(CURDIR)/py/tools/ovl.py
