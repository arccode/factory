# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This is the image for running integration tests for umpire docker. We use
# docker to ensure that everyone can run test in same environment.

FROM alpine:3.10
MAINTAINER Pi-Hsun Shih <pihsun@google.com>

ARG server_dir="/usr/local/factory"
ARG umpire_dir="${server_dir}/py/umpire"
ENV umpire_dir="${umpire_dir}"
ENV PYTHONPATH="${server_dir}/py_pkg"

# rsync: Used in e2e_test.py
# sudo: Used in cros_docker.sh.
RUN apk upgrade --no-cache && apk add --no-cache \
  bash \
  py3-pip \
  python3 \
  rsync \
  sudo

# add docker client -- Use the same version as we use in factory server image.
ADD build/docker/docker.tgz /

COPY py_pkg "${server_dir}/py_pkg/"
COPY bin "${server_dir}/bin/"

# copy requirements.txt and install in dependencies first, so we don't need to
# do this again if requirements.txt hasn't been modified
COPY py/umpire/server/e2e_test/requirements.txt \
  "${umpire_dir}/server/e2e_test/requirements.txt"
RUN pip3 install --no-cache-dir -r \
  "${umpire_dir}/server/e2e_test/requirements.txt"

COPY setup/cros_docker.sh "${server_dir}/setup/"
COPY py "${server_dir}/py/"

CMD "${umpire_dir}/server/e2e_test/e2e_test.py"
