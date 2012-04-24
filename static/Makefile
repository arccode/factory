# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

BUILD_DEPS=../../../build_deps

CLOSURE_LIB_VERSION=20111110-r1376

CLOSURE_LIB_ARCHIVE := $(BUILD_DEPS)/closure_library/closure-library-
CLOSURE_LIB_ARCHIVE := $(CLOSURE_LIB_ARCHIVE)$(CLOSURE_LIB_VERSION).tar.bz2
CLOSURE_LIB_DIR := $(BUILD_DEPS)/closure_library/closure-library-
CLOSURE_LIB_DIR := $(CLOSURE_LIB_DIR)$(CLOSURE_LIB_VERSION)

CLOSURE_COMPILER_JAR=/opt/closure-compiler-bin-0/lib/closure-compiler-bin.jar

CSS_SOURCES=\
    goog/css/dialog.css \
    goog/css/menu.css \
    goog/css/menuitem.css \
    goog/css/submenu.css \
    goog/css/tooltip.css \
    goog/css/tree.css \

CLOSURE_BUILD=\
    $(CLOSURE_LIB_DIR)/closure/bin/build/closurebuilder.py \
    --root $(CLOSURE_LIB_DIR) \
    --root ../js \
    -n cros.factory.Goofy \
    --compiler_jar=$(CLOSURE_COMPILER_JAR) \
    -f \
    --warning_level=VERBOSE

.PHONY: all
all: goofy.js closure.css

# For now, we just use the compiler (--output_mode=compiled) to check
# the correctness of our code, and we actually deploy the version that is
# just the concatenation of all the dependencies (--output_mode=script).
goofy.js: ../js/goofy.js $(CLOSURE_LIB_ARCHIVE)
	tar xf $(CLOSURE_LIB_ARCHIVE) -C $(dir $(CLOSURE_LIB_DIR))
	$(CLOSURE_BUILD) --output_mode=compiled --output_file=/dev/null
	$(CLOSURE_BUILD) --output_mode=script --output_file=$@

closure.css: $(addprefix $(CLOSURE_LIB_DIR)/closure/,\
                      $(CSS_SOURCES))
	cat $^ > $@

.PHONY: clean
clean:
	rm -f goofy.js closure.css
