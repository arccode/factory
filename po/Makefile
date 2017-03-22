# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

MK_DIR := ../devtools/mk
include $(MK_DIR)/common.mk

GETTEXT = $(MK_DIR)/pygettext.py
MSGFMT = msgfmt
MSGMERGE = msgmerge
MSGCAT = msgcat

KEYWORDS = -k _ -k MakeI18nLabel -k MakeI18nLabelWithClass -c i18n-label \
  -j _ -j i18nLabel -j i18nLabelNode -J "i18n! "

DOMAIN = factory
BUILD_DIR ?= ../build
PO_DIR ?= .
OUTPUT_DIR ?= $(BUILD_DIR)/locale
TEMP_DIR ?= $(BUILD_DIR)/po

BOARD_PO_DIR ?= $(if $(BOARD_FILES_DIR),$(BOARD_FILES_DIR)/po)

func-get-source-list = \
  $(sort $(wildcard \
    $(1)/goofy/*.py $(1)/goofy/*/*.py \
    $(1)/test/*.py $(1)/test/pytests/*.py \
    $(1)/test/pytests/*/*.py $(1)/test/test_lists/*.py \
    $(1)/test/pytests/*.html $(1)/test/pytests/*/*.html \
    $(1)/goofy/js/*.js $(1)/goofy/static/index.html \
    $(1)/goofy/static/ui_templates/*.html $(1)/test/pytests/*/*.js \
    $(1)/test/test_lists/*.test-list.json))

PY_ROOT = ../py
SRC_LIST = $(call func-get-source-list,$(PY_ROOT))
BOARD_SRC_LIST = $(if $(BOARD_FILES_DIR), \
  $(call func-get-source-list,$(BOARD_FILES_DIR)/py))

SRCS = $(wildcard $(PO_DIR)/*.po) \
  $(if $(BOARD_PO_DIR),$(wildcard $(BOARD_PO_DIR)/*.po))
LOCALES = $(sort $(foreach src,$(SRCS),$(basename $(notdir $(src)))))

LOCALE ?=
TARGET_PO = $(if $(BOARD_PO_DIR),$(BOARD_PO_DIR),$(PO_DIR))/$(LOCALE).po

func-update-po = \
  $(if $(wildcard $(1)),, \
    mkdir -p $(dir $(1)) $(\n) \
    sed "s/PO_REVISION_DATE/$(shell date +'%Y-%m-%d %H:%M+%Z')/; \
      s/LOCALE/$(basename $(notdir $(1)))/" po-header > $(1) $(\n)) \
  $(MSGMERGE) --force-po $(1) $(TEMP_DIR)/messages.pot \
    -o $(TEMP_DIR)/tmp.po $(\n) \
  mv -f $(TEMP_DIR)/tmp.po $(1) $(\n)

func-gettext-and-update-po = \
  $(if $(strip $(2)), \
    mkdir -p $(TEMP_DIR) $(\n) \
    $(GETTEXT) $(KEYWORDS) -o $(TEMP_DIR)/messages.pot $(1) $(\n) \
    $(foreach file,$(2),$(call func-update-po,$(file))))

all: build

init:
	$(if $(LOCALE),, \
	  $(error "You must specify locale of target translation."))
	$(if $(wildcard $(PO_DIR)/$(LOCALE).po), \
	  $(error "$(PO_DIR)/$(LOCALE).po already exists."))
	$(if $(and $(BOARD_PO_DIR),$(wildcard $(BOARD_PO_DIR)/$(LOCALE).po)), \
	  $(error "$(LOCALE).po already exists in board overlay."))
	$(call func-gettext-and-update-po, \
	  $(BOARD_SRC_LIST) $(SRC_LIST),$(TARGET_PO))

update:
	$(if $(BOARD_PO_DIR), \
	  $(call func-gettext-and-update-po,$(BOARD_SRC_LIST) $(SRC_LIST), \
	    $(foreach locale,$(LOCALES), \
	      $(if $(wildcard $(PO_DIR)/$(locale).po),, \
	         $(BOARD_PO_DIR)/$(locale).po))) \
	  $(call func-gettext-and-update-po,$(BOARD_SRC_LIST), \
	    $(foreach locale,$(LOCALES), \
	      $(if $(wildcard $(PO_DIR)/$(locale).po), \
	        $(BOARD_PO_DIR)/$(locale).po))), \
	  $(call func-gettext-and-update-po,$(SRC_LIST), \
	    $(foreach locale,$(LOCALES),$(PO_DIR)/$(locale).po)))

build:
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

.PHONY: init build update clean
.SUFFIXES: .po .mo
