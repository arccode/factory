# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

BUILD_DEPS=../../../build_deps

DISTFILES_TARGET = /var/cache/distfiles/target/
CLOSURE_LIB_DIR ?= /opt/closure-library

ifneq "$(shell test -e $(CLOSURE_LIB_DIR) && echo yes)" "yes"
  $(info ***)
  $(info *** $(CLOSURE_LIB_DIR) does not exist.)
  $(info *** Perhaps it needs to be manually installed.  Run this:)
  $(info ***)
  $(info ***   sudo emerge closure-library)
  $(info ***)
  $(error Terminating)
endif

CLOSURE_COMPILER_JAR=/opt/closure-compiler-bin-0/lib/closure-compiler-bin.jar

CSS_SOURCES=\
    goog/css/checkbox.css \
    goog/css/common.css \
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
    -n cros.factory.DeviceManager \
    --compiler_jar=$(CLOSURE_COMPILER_JAR) \
    -f \
    --warning_level=VERBOSE

.PHONY: all
all: goofy.js closure.css

# For now, we just use the compiler (--output_mode=compiled) to check
# the correctness of our code, and we actually deploy the version that is
# just the concatenation of all the dependencies (--output_mode=script).
goofy.js: $(CLOSURE_LIB_DIR) ../js/goofy.js ../js/device_manager.js \
          ../js/diagnosis_tool.js
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

$(CSS_SOURCE_PATHS): $(CLOSURE_LIB_DIR)

closure.css: $(CSS_SOURCE_PATHS)
# Replace all references to URLs with resources in this project.
	cat $^ | sed -re 's/\/\/ssl\.gstatic\.com\/(closure|editor)/images/g' > $@

.PHONY: clean
clean:
	rm -rf $(CLOSURE_LIB_DIR) goofy.js closure.css
