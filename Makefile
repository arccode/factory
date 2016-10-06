# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SHELL := bash

# Local environment settings
MK_DIR=devtools/mk
BUILD_DIR=$(CURDIR)/build
TEMP_DIR ?= $(BUILD_DIR)/tmp
PAR_BUILD_DIR=$(BUILD_DIR)/par
PAR_NAME=factory.par
DESTDIR=$(BUILD_DIR)/image
TARGET_DIR=/usr/local/factory
PYTHON=python

# Build config settings
STATIC ?= false

DOC_TEMP_DIR = $(TEMP_DIR)/docsrc
DOC_ARCHIVE_PATH = $(BUILD_DIR)/doc.zip
DOC_OUTPUT_DIR = $(BUILD_DIR)/doc

# The list of binaries to install has been moved to misc/symlinks.yaml.

FACTORY=$(DESTDIR)/$(TARGET_DIR)
FACTORY_BUNDLE=$(FACTORY)/bundle

CLOSURE_DIR = py/goofy/static

OVERLORD_DEPS_URL ?= \
		gs://chromeos-localmirror/distfiles/overlord-deps-0.0.3.tar.gz

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

# Special variable (two blank lines) so we can invoke commands with $(foreach).
define \n


endef

PRESUBMIT_TARGETS := \
  presubmit-deps presubmit-lint presubmit-test presubmit-make_factory_package

# Virtual targets. The '.phony' is a special hack to allow making targets with
# wildchar (for instance, overlay-%) to be treated as .PHONY.
.PHONY: .phony default clean closure proto overlord ovl-bin par bundle doc \
	presubmit presubmit-chroot $(PRESUBMIT_TARGETS) \
	lint smartlint smart_lint  test testall

INSTALL_MASK=*.pyc \
	     *_unittest.py \
	     py/doc

# This must be the first rule.
default: closure

# Currently the only programs using Closure is in Goofy.
closure:
	$(MAKE) -C $(CLOSURE_DIR)

# Dependencies for overlord.
$(BUILD_DIR)/go:
	mkdir -p $(BUILD_DIR)
	gsutil cp $(OVERLORD_DEPS_URL) $(BUILD_DIR)/.
	tar -xf $(BUILD_DIR)/$(shell basename $(OVERLORD_DEPS_URL)) \
		-C $(BUILD_DIR)

# TODO(hungte) Change overlord to build out-of-tree.
overlord: $(BUILD_DIR)/go
	$(MAKE) -C go/src/overlord DEPS=false STATIC=$(STATIC)
	# To install, get go/bin/{overlord,ghost}, and go/src/overlord/app.

ovl-bin:
	# Create virtualenv environment
	rm -rf $(BUILD_DIR)/.env
	virtualenv $(BUILD_DIR)/.env
	# Build ovl binary with pyinstaller
	cd $(BUILD_DIR); \
	source $(BUILD_DIR)/.env/bin/activate; \
	pip install jsonrpclib ws4py pyinstaller; \
	pyinstaller --onefile $(CURDIR)/py/tools/ovl.py

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

# Creates build/doc and build/doc.zip, containing the factory SDK docs.
doc:
	rm -rf $(DOC_TEMP_DIR); mkdir -p $(DOC_TEMP_DIR)
	# Do the actual build in the DOC_TEMP_DIR directory, since we need to
	# munge the docs a bit.
	rsync -a doc/ $(DOC_TEMP_DIR)
	# Generate rst sources for test cases
	bin/generate_rsts -o $(DOC_TEMP_DIR)
	CROS_FACTORY_PY_ROOT=$(realpath py_pkg) $(MAKE) -C $(DOC_TEMP_DIR) html
	mkdir -p $(dir $(DOC_ARCHIVE_PATH))
	rm -rf $(DOC_OUTPUT_DIR)
	cp -r $(DOC_TEMP_DIR)/_build/html $(DOC_OUTPUT_DIR)
	(cd $(DOC_OUTPUT_DIR)/..; zip -qr9 - $(notdir $(DOC_OUTPUT_DIR))) \
	  >$(DOC_ARCHIVE_PATH)

install:
	mkdir -p $(FACTORY)
	rsync -a --chmod=go=rX $(addprefix --exclude ,$(INSTALL_MASK)) \
	  bin misc py py_pkg sh init $(FACTORY)
	ln -sf bin/gooftool bin/edid bin/hwid_tool ${FACTORY}
	mkdir -m755 -p ${DESTDIR}/var/log
	mkdir -m755 -p $(addprefix ${DESTDIR}/var/factory/,log state tests)
	ln -sf $(addprefix ../factory/log/,factory.log console.log) \
	    ${DESTDIR}/var/log

bundle: par doc
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
	cp $(DOC_ARCHIVE_PATH) $(FACTORY_BUNDLE)
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

presubmit-chroot:
	$(foreach target,$(PRESUBMIT_TARGETS),$(MAKE) -s $(target)${\n})

presubmit-lint:
	@$(MAKE) lint LINT_FILES="$(filter %.py,$(PRESUBMIT_FILES))" 2>/dev/null

presubmit-deps:
	@if ! py/tools/deps.py $(PRESUBMIT_FILES); then \
	  echo "Dependency check failed." ; \
	  echo "Please read py/tools/deps.conf for more information." ; \
	  exit 1; \
	fi

# Check that test_make_factory_package.py has been run, if
# make_factory_package.sh has changed.
presubmit-make-factory-package:
ifneq ($(filter setup/make_factory_package.sh,$(PRESUBMIT_FILES)),)
	@if [ ! setup/make_factory_package.sh -ot \
	      py/tools/.test_make_factory_package.passed ]; then \
	  echo "setup/make_factory_package.sh has changed."; \
	  echo "Please run py/tools/test_make_factory_package.py" \
	       "(use --help for more information on how to use it if" \
	       "you do not have access to release repositories)."; \
	  exit 1; \
	fi
endif

presubmit-test:
	@$(MK_DIR)/$@.sh $(PRESUBMIT_FILES)

presubmit:
ifeq ($(wildcard /etc/debian_chroot),)
	$(info Running presubmit checks inside chroot...)
	@cros_sdk PRESUBMIT_FILES="$(PRESUBMIT_FILES)" -- \
	  $(MAKE) -C ../platform/factory -s $@-chroot
else
	@$(MAKE) -s $@-chroot
endif

clean:
	rm -rf $(BUILD_DIR)

test:
	@TEST_EXTRA_FLAGS=$(TEST_EXTRA_FLAGS) \
		$(MK_DIR)/test.sh $(UNITTESTS_WHITELIST)

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

