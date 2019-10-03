# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

MK_DIR := ../devtools/mk
include $(MK_DIR)/common.mk

GETTEXT = $(MK_DIR)/pygettext.py
LIST_PYTESTS = ../bin/list_pytests
MSGFMT = msgfmt
MSGMERGE = msgmerge
MSGCAT = msgcat

KEYWORDS = -k _ -t i18n-label -j _ -j i18nLabel -j i18nLabelNode -J "i18n! "

DOMAIN = factory
BUILD_DIR ?= ../build
PO_DIR ?= .
OUTPUT_DIR ?= $(BUILD_DIR)/locale
TEMP_DIR ?= $(BUILD_DIR)/po

BOARD_PO_DIR ?= $(if $(BOARD_FILES_DIR),$(BOARD_FILES_DIR)/po)

func-get-source-list = \
  $(sort $(wildcard \
    $(1)/goofy/*.py $(1)/goofy/*/*.py $(1)/goofy/plugins/*/*.py \
    $(1)/test/*.py $(1)/test/fixture/*/*.py \
    $(1)/test/pytests/*.py $(1)/test/pytests/*/*.py \
    $(1)/test/test_lists/*.py \
    $(1)/goofy/plugins/*/*/*.html $(1)/goofy/static/*.html \
    $(1)/test/pytests/*/*.html $(1)/test/pytests/*/static/*.html \
    $(1)/goofy/js/*.js $(1)/goofy/plugins/*/*/*.js \
    $(1)/goofy/static/js/default_test_ui.js \
    $(1)/test/pytests/*/*.js $(1)/test/pytests/*/static/*.js \
    $(1)/config/*.test_list.json $(1)/test/test_lists/*.test_list.json))

PYTESTS_LABEL_FILE ?= $(BUILD_DIR)/pytests_label_generated.json
BOARD_PYTESTS_LABEL_FILE ?= $(BUILD_DIR)/board_pytests_label_generated.json

PY_ROOT = ../py
SRC_LIST = $(call func-get-source-list,$(PY_ROOT)) $(PYTESTS_LABEL_FILE)
BOARD_SRC_LIST = $(if $(BOARD_FILES_DIR), \
  $(call func-get-source-list,$(BOARD_FILES_DIR)/py) \
  $(BOARD_PYTESTS_LABEL_FILE))

SRCS = $(wildcard $(PO_DIR)/*.po) \
  $(if $(BOARD_PO_DIR),$(wildcard $(BOARD_PO_DIR)/*.po))
LOCALES = $(sort $(foreach src,$(SRCS),$(basename $(notdir $(src)))))

LOCALE ?=
TARGET_PO = $(if $(BOARD_PO_DIR),$(BOARD_PO_DIR),$(PO_DIR))/$(LOCALE).po

func-update-po = \
  $(if $(wildcard $(1)),, \
    mkdir -p $(dir $(1)) $(\n) \
    touch $(1) $(\n)) \
  sed "s/PO_REVISION_DATE/$(shell date +'%Y-%m-%d %H:%M+%Z')/; \
    s/LOCALE/$(basename $(notdir $(1)))/" po-header > \
    $(TEMP_DIR)/header.po $(\n) \
  $(MSGMERGE) --force-po $(1) $(TEMP_DIR)/messages.pot \
    -o $(TEMP_DIR)/tmp.po $(\n) \
  $(MSGMERGE) --force-po $(TEMP_DIR)/header.po $(TEMP_DIR)/tmp.po \
    -o $(TEMP_DIR)/final.po $(\n) \
  mv -f $(TEMP_DIR)/final.po $(1) $(\n)

func-gettext-and-update-po = \
  $(if $(strip $(2)), \
    mkdir -p $(TEMP_DIR) $(\n) \
    $(GETTEXT) $(KEYWORDS) -o $(TEMP_DIR)/messages.pot $(1) $(\n) \
    $(foreach file,$(2),$(call func-update-po,$(file))))

all: build

update_pytest_list:
	mkdir -p $(BUILD_DIR)
	$(LIST_PYTESTS) -l > $(PYTESTS_LABEL_FILE)
	$(if $(BOARD_FILES_DIR), $(LIST_PYTESTS) -l $(BOARD_FILES_DIR) \
	  > $(BOARD_PYTESTS_LABEL_FILE))

init: update_pytest_list
	$(if $(LOCALE),, \
	  $(error "You must specify locale of target translation."))
	$(if $(wildcard $(PO_DIR)/$(LOCALE).po), \
	  $(error "$(PO_DIR)/$(LOCALE).po already exists."))
	$(if $(and $(BOARD_PO_DIR),$(wildcard $(BOARD_PO_DIR)/$(LOCALE).po)), \
	  $(error "$(LOCALE).po already exists in board overlay."))
	$(call func-gettext-and-update-po, \
	  $(BOARD_SRC_LIST) $(SRC_LIST),$(TARGET_PO))

update: update_pytest_list
	$(if $(BOARD_PO_DIR), \
	  $(info Updating overlay-only locales) \
	  $(call func-gettext-and-update-po,$(BOARD_SRC_LIST) $(SRC_LIST), \
	    $(foreach locale,$(LOCALES), \
	      $(if $(wildcard $(PO_DIR)/$(locale).po),, \
	         $(BOARD_PO_DIR)/$(locale).po))) \
	  $(info Updating other locales) \
	  $(call func-gettext-and-update-po,$(BOARD_SRC_LIST), \
	    $(foreach locale,$(LOCALES), \
	      $(if $(wildcard $(PO_DIR)/$(locale).po), \
	        $(BOARD_PO_DIR)/$(locale).po))), \
	  $(info Updating public locales) \
	  $(call func-gettext-and-update-po,$(SRC_LIST), \
	    $(foreach locale,$(LOCALES),$(PO_DIR)/$(locale).po)))

build:
	rm -rf $(OUTPUT_DIR)
	$(foreach locale,$(LOCALES), \
	  mkdir -p $(OUTPUT_DIR)/$(locale)/LC_MESSAGES $(\n) \
	  $(MSGCAT) -o - --use-first \
	    $(wildcard \
	      $(if $(BOARD_PO_DIR),$(BOARD_PO_DIR)/$(locale).po) \
	      $(PO_DIR)/$(locale).po) \
	    | $(MSGFMT) -o $(OUTPUT_DIR)/$(locale)/LC_MESSAGES/$(DOMAIN).mo - \
	  $(\n))

clean:
	rm -rf $(TEMP_DIR) $(OUTPUT_DIR)

.PHONY: all update_pytest_list init update build clean
.SUFFIXES: .po .mo
