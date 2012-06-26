# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

BUILD_DEPS=../../../build_deps

CLOSURE_LIB_VERSION=20111110-r1376

CLOSURE_LIB_ARCHIVE := /var/cache/distfiles/target/cros-binary/closure-library-$(CLOSURE_LIB_VERSION).tar.bz2
CLOSURE_LIB_DIR := $(or $(WORKDIR),/tmp)/closure-library-$(CLOSURE_LIB_VERSION)

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
    $(CLOSURE_LIB_DIR)/closure/bin/build/closurebuilder.py \
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
	tar xf $< -C $(dir $(CLOSURE_LIB_DIR))
	touch $@

# For now, we just use the compiler (--output_mode=compiled) to check
# the correctness of our code, and we actually deploy the version that is
# just the concatenation of all the dependencies (--output_mode=script).
goofy.js: $(EXTRACTED) ../js/goofy.js
	$(CLOSURE_BUILD) --output_mode=compiled --output_file=/dev/null
	$(CLOSURE_BUILD) --output_mode=script --output_file=$@

$(CSS_SOURCE_PATHS): $(EXTRACTED)

closure.css: $(CSS_SOURCE_PATHS)
	cat $^ > $@

.PHONY: clean
clean:
	rm -rf $(CLOSURE_LIB_DIR) goofy.js closure.css
