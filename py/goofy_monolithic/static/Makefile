# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

BUILD_DEPS=../../../build_deps

CLOSURE_LIB_VERSION=20130212-95c19e7f0f5f

DISTFILES_TARGET = /var/cache/distfiles/target/
CLOSURE_LIB_ARCHIVE := \
  $(DISTFILES_TARGET)/closure-library-$(CLOSURE_LIB_VERSION).zip
CLOSURE_LIB_DIR := $(or $(WORKDIR),/tmp)/closure-library-$(CLOSURE_LIB_VERSION)

ifneq "$(shell test -e $(CLOSURE_LIB_ARCHIVE) && echo yes)" "yes"
  DEFAULT_BOARD=$(or $(shell cat $$HOME/trunk/src/scripts/.default_board \
                       2>/dev/null),x86-generic)
  $(info ***)
  $(info *** $(CLOSURE_LIB_ARCHIVE) does not exist.)
  $(info *** Perhaps it needs to be downloaded from BCS.  Run this:)
  $(info *** (you can use any board))
  $(info ***)
  $(info ***   emerge-$(DEFAULT_BOARD) chromeos-factory)
  $(info ***)
  $(error Terminating)
endif

CLOSURE_COMPILER_JAR=/opt/closure-compiler-bin-0/lib/closure-compiler-bin.jar

CSS_SOURCES=\
    goog/css/checkbox.css \
    goog/css/dialog.css \
    goog/css/menu.css \
    goog/css/menuitem.css \
    goog/css/menuseparator.css \
    goog/css/submenu.css \
    goog/css/tooltip.css \
    goog/css/tree.css

CSS_SOURCE_PATHS=$(addprefix $(CLOSURE_LIB_DIR)/closure/,$(CSS_SOURCES))

CLOSURE_BUILD=\
    python $(CLOSURE_LIB_DIR)/closure/bin/build/closurebuilder.py \
    --root $(CLOSURE_LIB_DIR) \
    --root ../js \
    -n cros.factory.Goofy \
    --compiler_jar=$(CLOSURE_COMPILER_JAR) \
    -f \
    --warning_level=VERBOSE

.PHONY: all
all: goofy.js closure.css

# Dummy file to represent extraction of the tarball.
EXTRACTED=$(CLOSURE_LIB_DIR)/.extracted
$(EXTRACTED): $(CLOSURE_LIB_ARCHIVE)
	rm -rf $(CLOSURE_LIB_DIR)
	mkdir -p $(CLOSURE_LIB_DIR)
	unzip -qd $(CLOSURE_LIB_DIR) $<
	touch $@

# For now, we just use the compiler (--output_mode=compiled) to check
# the correctness of our code, and we actually deploy the version that is
# just the concatenation of all the dependencies (--output_mode=script).
goofy.js: $(EXTRACTED) ../js/goofy.js
	mkdir -p tmp
	$(CLOSURE_BUILD) --output_mode=compiled --output_file=/dev/null \
	    >& tmp/errors.compiled || ( cat tmp/errors.compiled; exit 1 )
	if fgrep "WARNING -" tmp/errors.compiled; then \
	  cat tmp/errors.compiled; \
	  echo Warning found in compiler output.; \
	  echo Set GOOFY_ALLOW_WARNINGS=1 to prevent aborting.; \
	  $(if $(not $(GOOFY_ALLOW_WARNINGS)),exit 1;) \
	fi
	$(CLOSURE_BUILD) --output_mode=script --output_file=$@ >& tmp/errors.script \
	    >& tmp/errors.script || ( cat tmp/errors.script; exit 1 )
	rm -rf tmp

$(CSS_SOURCE_PATHS): $(EXTRACTED)

closure.css: $(CSS_SOURCE_PATHS)
# Replace all references to URLs with resources in this project.
	cat $^ | sed -re 's/\/\/ssl\.gstatic\.com\/(closure|editor)/images/g' > $@

.PHONY: clean
clean:
	rm -rf $(CLOSURE_LIB_DIR) goofy.js closure.css
