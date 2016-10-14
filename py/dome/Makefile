# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

define DOME_MAKE_HELP_MESSAGE
Usage: $(MAKE) TARGET

Targets:
  lint           lint both back-end and front-end files
  lint-backend   lint back-end files
  lint-frontend  lint front-end files
  test           run back-end and front-end end-to-end tests
  test-backend   run back-end end-to-end tests
  test-frontend  run front-end end-to-end tests
endef
export DOME_MAKE_HELP_MESSAGE

.PHONY: help lint-backend lint-frontend test-backend test-frontend

all: help

help:
	@echo "$${DOME_MAKE_HELP_MESSAGE}"

lint: lint-backend lint-frontend

lint-backend:
	make -C ../.. lint \
		LINT_FILES="py/dome/backend/*.py py/dome/backend/migrations/*.py"

lint-frontend:
	../../setup/dome.sh build
	docker run --rm cros/dome-builder npm run lint

test: test-backend test-frontend

test-backend:
	../../setup/dome.sh build
	docker run cros/dome python manage.py test

test-frontend:
	echo "not implemented yet"
