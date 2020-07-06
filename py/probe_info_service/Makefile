# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This Makefile provides different targets:
# - prepare: Generates the protobuf modules in the build directory.
# - _pack: Packages the required files together in preparation of deploying
#     to AppEngine.  This target is expected to be called by the deploy script.

PACKAGE_PATH_NAME = cros/factory/probe_info_service

FACTORY_DIR = ../..
FACTORY_PY_PKG_DIR = $(FACTORY_DIR)/py_pkg
PACKAGE_PRIVATE_DIR = \
	$(FACTORY_DIR)/../factory-private/config/probe_info_service
BUILD_DIR := $(FACTORY_DIR)/build/probe_info_service
GEN_CODE_DIR = $(BUILD_DIR)/gen
PACK_DEST_DIR :=

PROTO_SRC_FILES = app_engine/stubby.proto app_engine/client_payload.proto
PROTO_PYGEN_FILES = $(patsubst \
	%.proto,$(GEN_CODE_DIR)/$(PACKAGE_PATH_NAME)/%_pb2.py, \
	$(PROTO_SRC_FILES))

APPENGINE_CONFIGS = app_engine/requirements.txt app_engine/app.yaml

DEP_PACKAGE_PATH_NAMES = cros/factory/utils cros/factory/probe/runtime_probe

.PHONY: prepare _pack clean

prepare: $(PROTO_PYGEN_FILES)

clean:
	rm -rf "$(BUILD_DIR)"

$(GEN_CODE_DIR)/$(PACKAGE_PATH_NAME)/%_pb2.py: %.proto
	mkdir -p "$(GEN_CODE_DIR)/$(PACKAGE_PATH_NAME)" || true
	protoc --python_out="$(GEN_CODE_DIR)/$(PACKAGE_PATH_NAME)" "$<"

_pack: prepare
	$(if $(PACK_DEST_DIR),, \
	  $(error "You must specify the dest directory by `PACK_DEST_DIR`."))
	mkdir -p "$(PACK_DEST_DIR)/$(PACKAGE_PATH_NAME)"
	find . ! -type d ! -name "*.pyc" -exec \
	    cp --parents "{}" "$(PACK_DEST_DIR)/$(PACKAGE_PATH_NAME)" ";"
	cp -r . "$(PACK_DEST_DIR)/$(PACKAGE_PATH_NAME)"
	for path_name in $(DEP_PACKAGE_PATH_NAMES); \
	  do \
	    mkdir -p "$(PACK_DEST_DIR)/$${path_name}"; \
	    ( \
	      cd "$(FACTORY_PY_PKG_DIR)/$${path_name}"; \
	      find . ! -type d ! -name "*_*test.py" ! -name "*.pyc" -exec \
	          cp --parents "{}" "$(PACK_DEST_DIR)/$${path_name}" ";" \
	    ); \
	  done
	cp -Trf "$(PACKAGE_PRIVATE_DIR)" "$(PACK_DEST_DIR)/$(PACKAGE_PATH_NAME)"
	cp -r "$(GEN_CODE_DIR)/"* "$(PACK_DEST_DIR)"
	cp $(APPENGINE_CONFIGS) "$(PACK_DEST_DIR)"
