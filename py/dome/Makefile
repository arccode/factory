# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

define DOME_MAKE_HELP_MESSAGE
Usage: $(MAKE) TARGET

Targets:
  lint           lint both back-end and front-end files
  lint-backend   lint back-end files
  lint-frontend  lint front-end files
endef
export DOME_MAKE_HELP_MESSAGE

.PHONY: .phony

all: help

help: .phony
	@echo "$${DOME_MAKE_HELP_MESSAGE}"

lint: lint-backend lint-frontend

lint-backend: .phony
	make -C ../.. lint \
	  LINT_FILES="py/dome/backend/*.py py/dome/backend/migrations/*.py"

lint-frontend: .phony
	../../setup/dome.sh build
	docker run --rm cros/dome-builder npm run lint
