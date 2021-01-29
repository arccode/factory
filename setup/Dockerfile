# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM alpine:3.10
MAINTAINER Mao Huang <littlecvr@google.com>

# need to explicitly assign PYTHONPATH for uwsgi
ENV PYTHONPATH="/usr/local/factory/py_pkg"

ARG server_dir="/usr/local/factory"
ARG dome_dir="${server_dir}/py/dome"
ARG instalog_dir="${server_dir}/py/instalog"
ARG umpire_dir="${server_dir}/py/umpire"
ARG umpire_dir_in_dome

ARG overlord_output_file="overlord.tar.gz"
ARG dome_builder_output_file="frontend.tar"

# add docker client -- do not install docker via apk -- it will try to install
# docker engine which takes a lot of space as well (we don't need it, we need
# only the small client to communicate with the host's docker server)
ADD build/docker/docker.tgz /

# Install packages. Python packages should be installed by pip if possible.
# However, uwsgi-python and psutil from pip needs to build from source, Twisted
# has package signing problem, so we will install them using apk.
#
#  pigz, py-pip, py-twisted, py-yaml, python, tar: Used by Umpire
#  py-lxml: Used by zeep (SOAP), indirectly imported by Umpire
#  (buzybox tar doesn't support -I, which is used in file_utils.ExtractFile)
#  gnupg, python-gnupg: Used by umpire/server/service/dkps and archiver
#  rsync: Used by umpire/server/service/rsync
#  curl, jq: Used by cros_payload.
#
#  nginx, uwsgi-python, dnsmasq: Used by Dome.
#
#  apache2-utils, openssl: Used by Overlord setup.sh
#
#  util-linux: For GNU mount since busybox mount doesn't support offset.
#  coreutils: For GNU mktemp since busybox mktemp doesn't support --tmpdir.
#
#  py-psutil: Dependencies for Python package gnupg that is used by Instalog.
RUN apk upgrade --no-cache && apk add --no-cache \
    apache2-utils \
    coreutils \
    curl \
    dnsmasq \
    gnupg \
    file \
    jq \
    nginx \
    openssl \
    pigz \
    py3-lxml \
    py3-pip \
    py3-psutil \
    py3-twisted \
    python3 \
    rsync \
    tar \
    unzip \
    util-linux \
    uwsgi-python3 \
    xz

# The latest cffi (1.14.3) would always build from source, which requires the
# follow packages.
# TODO(b/169730131): revert this when we can install prebuilt cffi again.
RUN apk add --no-cache \
    build-base \
    python3-dev \
    libffi-dev

# pixz and lbzip2 are not available in alpine.
ADD build/docker/pixz.tbz2 /usr/bin
ADD build/docker/lbzip2.tbz2 /usr/bin

# Add self-built UFTP binary
ADD build/docker/uftp.tgz /usr/bin

# Prepare requirements file and install pip packages.
COPY py/umpire/server/requirements.txt "${umpire_dir}/"
COPY py/dome/requirements.txt "${dome_dir}/"
COPY py/instalog/requirements.txt "${instalog_dir}/"
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir --upgrade setuptools && \
    pip3 install --no-cache-dir --upgrade wheel
RUN pip3 install --no-cache-dir \
      -r "${umpire_dir}/requirements.txt" \
      -r "${dome_dir}/requirements.txt" \
      -r "${instalog_dir}/requirements.txt"

# Create Umpire mount point. Normally we should mount this (and Docker will
# create it for us) when calling the run command, but that's not the case for
# unit tests. Not creating this directory may cause unit tests to fail.
RUN mkdir -p "${umpire_dir_in_dome}"

RUN ln -s "${server_dir}/bin/umpire" /usr/local/bin/
RUN ln -s "${instalog_dir}/cli.py" /usr/bin/instalog

# these files are unlikely to change often, put them here to take advantage of
# docker's cache
COPY py/dome/nginx.conf /etc/nginx/

ADD "build/docker/${overlord_output_file}" "${server_dir}/bin/"

# these files are likely to change often, put them at the end
ADD "build/docker/${dome_builder_output_file}" "${dome_dir}/static/"

COPY py_pkg "${server_dir}/py_pkg"
COPY bin "${server_dir}/bin"
COPY sh "${server_dir}/sh"
COPY py "${server_dir}/py"

# These arguments change every time and ARG instructions will affect all
# following RUN instructions. We should put them in the end of Dockerfile to
# avoid making Docker cache mechanism useless.
ARG docker_image_githash
ARG docker_image_islocal
ARG docker_image_timestamp
ENV DOCKER_IMAGE_GITHASH="${docker_image_githash}"
ENV DOCKER_IMAGE_ISLOCAL="${docker_image_islocal}"
ENV DOCKER_IMAGE_TIMESTAMP="${docker_image_timestamp}"
