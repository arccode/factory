# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

OUTPUT_DIR = .
OUTPUT_JS = $(OUTPUT_DIR)/js/goofy.js
OUTPUT_CSS = $(OUTPUT_DIR)/css/closure.css

BUILD_DEPS = ../../../build_deps
CLOSURE_LIB_DIR = /opt/closure-library
CLOSURE_COMPILER_JAR = /opt/closure-compiler-bin-0/lib/closure-compiler-bin.jar

JS_SOURCES = \
    goofy.js \
    device_manager.js \
    diagnosis_tool.js

JS_SOURCE_PATHS=$(addprefix ../js/,$(JS_SOURCES))

CSS_SOURCES = \
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

.PHONY: all clean

all: $(OUTPUT_JS) $(OUTPUT_CSS)

clean:
	rm -f $(OUTPUT_JS) $(OUTPUT_CSS)

check_deps:
	$(if $(wildcard $(CLOSURE_LIB_DIR)),,\
	  $(info *** $(CLOSURE_LIB_DIR) does not exist.) \
	  $(info *** Please install it. For example, run this in chroot:) \
	  $(info ***) \
	  $(info ***   sudo emerge closure-library) \
	  $(info ***) \
	  $(error Terminating))

$(OUTPUT_JS): $(JS_SOURCE_PATHS) | check_deps
	$(call func-check-closure)
	mkdir -p "$(shell dirname "$@")"
	# For now, we just use the compiler (--output_mode=compiled) to check
	# the correctness of our code, and we actually deploy the version that
	# is the concatenation of all the dependencies (--output_mode=script).
	$(CLOSURE_BUILD) --output_mode=compiled --output_file=/dev/null
	$(CLOSURE_BUILD) --output_mode=script --output_file=$@

$(OUTPUT_CSS): $(CSS_SOURCE_PATHS) | check_deps
	# Replace all references to URLs with resources in this project.
	mkdir -p "$(shell dirname "$@")"
	sed -re 's"//ssl\.gstatic\.com/(closure|editor)"/images"g' $^ >$@
