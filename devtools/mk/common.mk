# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Trick to only expand variable at most once. Can be used to avoid repetitive
# expensive calculation.
# Usage:
#   _SOME_VAR = $(shell some-expensive-calculation)
#   SOME_VAR = $(call memoized,_SOME_VAR)
memoized = $(if $(__var_$1),,$(eval __var_$1 := $($1)))$(__var_$1)

# Special variable (two blank lines) so we can invoke commands with $(foreach).
define \n


endef

BOARD ?=
# The package names (factory-board, chromeos-factory-board) must be same as
# RDEPEND listed in virtual/chromeos-bsp-factory.
_BOARD_EBUILD = \
  $(if $(BOARD),$(shell equery-$(BOARD) which factory-board 2>/dev/null || \
                        equery-$(BOARD) which chromeos-factory-board))
BOARD_EBUILD ?= $(call memoized,_BOARD_EBUILD)
BOARD_FILES_DIR ?= $(if $(BOARD_EBUILD),$(dir $(BOARD_EBUILD))files)

_BASEBOARD_EBUILD = \
  $(if $(BOARD),$(shell equery-$(BOARD) which factory-baseboard))

BASEBOARD_EBUILD ?= $(call memoized,_BASEBOARD_EBUILD)
BASEBOARD_FILES_DIR ?= $(if $(BASEBOARD_EBUILD),$(dir $(BASEBOARD_EBUILD))files)
