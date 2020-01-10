# Copyright 2012 The Chromium OS Authors. All rights reserved.
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

DOME_DIR=/usr/local/factory/py/dome

# Command used to analyze test coverage in target 'test-backend'.
TEST_COVERAGE_CMD = \
	mkdir /tmp/shared && \
	coverage run \
		--source="." \
		--omit="backend/migrations/*" \
		manage.py test && \
	coverage report && \
	coverage html --directory="build/test_coverage_report"

.PHONY: help lint-backend lint-frontend test-backend test-frontend

all: help

help:
	@echo "$${DOME_MAKE_HELP_MESSAGE}"

lint: lint-backend lint-frontend

lint-backend:
	make -C ../.. lint \
		LINT_FILES="py/dome/backend/*.py py/dome/backend/migrations/*.py"

lint-frontend:
	../../setup/cros_docker.sh build
	docker run --rm cros/dome-builder npm run lint

test: test-frontend test-backend
	touch .tests-passed

test-backend:
	../../setup/cros_docker.sh build
	# TODO(b/34117401): remove hard-coded path
	docker run \
		--rm \
		--volume "$(CURDIR)/../../build/docker:/usr/local/factory/py/dome/build" \
		--volume "/cros_docker/dome/test_log:/var/log/dome" \
		--workdir "${DOME_DIR}" \
		cros/factory_server \
		sh -c "$(TEST_COVERAGE_CMD)"

test-frontend:
	echo "Running dome frontend test"
	../../setup/cros_docker.sh build
	docker run --rm cros/dome-builder npm run test
