# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# A docker file to provide minimal build environment for ChromeOS Factory SDK.

FROM debian:testing
MAINTAINER Hung-Te Lin <hungte@chromium.org>

# Install packages.
RUN apt-get update
RUN apt-get install -y --no-install-recommends \
    bzip2 \
    ca-certificates \
    curl \
    gettext \
    git \
    lbzip2 \
    make \
    makeself \
    openssl \
    python \
    python-enum34 \
    python-jsonrpclib \
    python-openssl \
    python-pip \
    python-protobuf \
    python-setuptools \
    python-yaml \
    rsync \
    unzip \
    zip

RUN pip install gsutil

RUN rm -rf /var/lib/apt/lists/*
