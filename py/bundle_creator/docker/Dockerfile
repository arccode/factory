# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM google/cloud-sdk
LABEL maintainer="Ting Shen <phoenixshen@google.com>"

EXPOSE 8000

RUN apt-get update && apt-get install -y \
    bzip2 \
    cgpt \
    curl \
    gcc \
    git \
    libssl-dev \
    lsb-release \
    moreutils \
    nginx \
    pbzip2 \
    pigz \
    python-dev \
    python-setuptools \
    rsync \
    sharutils \
    sudo \
    unzip \
    vboot-utils \
    vim \
    xz-utils

# use latest version of pip
# https://bugs.launchpad.net/ubuntu/+source/python-pip/+bug/1306991
RUN easy_install pip

COPY docker/requirements.txt /root/
RUN pip install -r /root/requirements.txt

ARG GS_BASE="gs://chromeos-releases/dev-channel"
ARG BOARD="grunt"
ARG VERSION="12522.0.0"
ARG TOOLKIT="${GS_BASE}/${BOARD}/${VERSION}/*-factory-*.zip"
COPY docker/service_account.json /
RUN gcloud auth activate-service-account --key-file=/service_account.json && \
    gsutil cp "${TOOLKIT}" /tmp/factory.zip
RUN unzip -o /tmp/factory.zip toolkit/install_factory_toolkit.run -d /tmp
RUN /tmp/toolkit/install_factory_toolkit.run -- --non-cros --yes
ENV PYTHONPATH=/usr/local/factory/py
ENV GOOGLE_APPLICATION_CREDENTIALS=/service_account.json

# set user name for finalize_bundle
ENV USER bundle_creator

COPY . /usr/local/factory/py/bundle_creator/

CMD gcloud auth activate-service-account --key-file=/service_account.json && \
    python2 /usr/local/factory/py/bundle_creator/docker/worker.py

