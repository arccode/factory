# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

DESTDIR ?=
CHROMITE_LIB_PATH ?= ../../../../../chromite/lib
BIN_DIR := /usr/bin
LIB_DIR := /usr/local/hwid_extractor

CLI_SOURCES := \
		factory_env.py \
		hwid_extractor.py

UTILS_SOURCES := \
		__init__.py \
		file_utils.py \
		platform_utils.py \
		process_utils.py \
		type_utils.py

HWID_EXTRACTOR_SOURCES := \
	www/index.html \
	$(wildcard *.py)

SOURCES := \
	$(addprefix cli/,$(CLI_SOURCES)) \
	$(addprefix hwid_extractor/,$(HWID_EXTRACTOR_SOURCES)) \
	$(addprefix utils/,$(UTILS_SOURCES))

CHROMITE_AP_CONFIG := \
	$(wildcard $(CHROMITE_LIB_PATH)/firmware/ap_firmware_config/*.py)
CHROMITE_SOURCES := \
	__init__.py \
	buildbot_annotations.py \
	cros_logging.py \
	firmware/__init__.py \
	firmware/servo_lib.py \
	$(CHROMITE_AP_CONFIG:$(CHROMITE_LIB_PATH)/%=%)

INSTALL_TARGET := $(addprefix install_,$(SOURCES))
CHROMITE_INSTALL_TARGET := $(addprefix install_,$(CHROMITE_SOURCES))

.PHONY: all $(INSTALL_TARGET) $(CHROMITE_INSTALL_TARGET) install

all:

$(INSTALL_TARGET):
	mkdir -p $(DESTDIR)$(LIB_DIR)/py/$(dir $(@:install_%=%))
	cp -P ../$(@:install_%=%) $(DESTDIR)$(LIB_DIR)/py/$(@:install_%=%)

$(CHROMITE_INSTALL_TARGET):
	mkdir -p \
		$(DESTDIR)$(LIB_DIR)/py_pkg/chromite/lib/$(dir $(@:install_%=%))
	cp -P $(CHROMITE_LIB_PATH)/$(@:install_%=%) \
		$(DESTDIR)$(LIB_DIR)/py_pkg/chromite/lib/$(@:install_%=%)

install: $(INSTALL_TARGET) $(CHROMITE_INSTALL_TARGET)
	# Setup py_pkg/cros
	mkdir -p $(DESTDIR)$(LIB_DIR)/py_pkg/cros
	touch $(DESTDIR)$(LIB_DIR)/py_pkg/cros/__init__.py

	# Setup py_pkg/cros/factory
	ln -sf ../../py $(DESTDIR)$(LIB_DIR)/py_pkg/cros/factory
	mkdir -p $(DESTDIR)$(BIN_DIR)

	# Setup hwid_extractor execuable
	ln -sf ../..$(LIB_DIR)/py/cli/factory_env.py \
			$(DESTDIR)$(BIN_DIR)/hwid_extractor

	# Setup py_pkg/chromite/lib
	mkdir -p $(DESTDIR)$(LIB_DIR)/py_pkg/chromite/lib
	touch $(DESTDIR)$(LIB_DIR)/py_pkg/chromite/__init__.py
	touch $(DESTDIR)$(LIB_DIR)/py_pkg/chromite/lib/__init__.py
