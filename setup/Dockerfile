# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM alpine:3.4
MAINTAINER Mao Huang <littlecvr@google.com>

# need to explicitly assign PYTHONPATH for uwsgi
ENV PYTHONPATH="/usr/local/lib/python2.7/site-packages"

ARG server_dir="/usr/local/factory"
ARG dome_dir="${server_dir}/py/dome"
ARG instalog_dir="${server_dir}/py/instalog"
ARG umpire_dir_in_dome

# Create Umpire mount point. Normally we should mount this (and Docker will
# create it for us) when calling the run command, but that's not the case for
# unit tests. Not creating this directory may cause unit tests to fail.
RUN mkdir -p "${umpire_dir_in_dome}"

# pigz, py-pip, py-twisted, py-yaml, python, lighttpd, tar: Used by Umpire
# (buzybox tar doesn't support -I, which is used in file_utils.ExtractFile)
# gnupg, python-gnupg: Used by umpire/service/archiver
# py-flup: Used by umpire/service/absub_logparser
# rsync: Used by umpire/service/rsync

# py-protobuf: Dependencies that are used by some board's shop_floor

# nginx, uwsgi-python: Used by Dome
# cannot install uwsgi using pip since we don't have compiler

# apache2-utils, openssl: Used by Overlord setup.sh

# util-linux: For GNU mount since busybox mount doesn't support offset.
# coreutils: For GNU mktemp since busybox mktemp doesn't support --tmpdir.
RUN apk upgrade --no-cache && apk add --no-cache \
  apache2-utils \
  coreutils \
  gnupg \
  lighttpd \
  nginx \
  openssl \
  pigz \
  py-flup \
  py-pip \
  py-twisted \
  py-yaml \
  python \
  rsync \
  tar \
  unzip \
  util-linux \
  uwsgi-python \
  && apk add --no-cache \
  --repository http://dl-3.alpinelinux.org/alpine/edge/testing/ \
  py-protobuf \
  lbzip2 \
  && ln -s /usr/bin/lbzip2 /usr/bin/pbzip2 \
  && pip install \
  python-gnupg

COPY py_pkg "${server_dir}/py_pkg/"
COPY bin "${server_dir}/bin/"

# add docker client -- do not install docker via apk -- it will try to install
# docker engine which takes a lot of space as well (we don't need it, we need
# only the small client to communicate with the host's docker server)
ADD build/docker/docker.tgz /

# Use pre-built static binaries (cgpt), since there's no package for
# those in alpine.
ARG umpire_builder_output_file="bins.tar"
ADD "build/docker/${umpire_builder_output_file}" /usr/local/bin/

# these files are unlikely to change often, put them here to take advantage of
# docker's cache
COPY py/dome/nginx.conf /etc/nginx/nginx.conf
COPY py/dome/uwsgi.ini py/dome/manage.py py/dome/requirements.txt "${dome_dir}/"
RUN pip install --no-cache-dir -r "${dome_dir}/requirements.txt"
COPY py/instalog/requirements.txt "${instalog_dir}/"
RUN pip install --no-cache-dir -r "${instalog_dir}/requirements.txt"

ARG overlord_output_file="overlord.tar.gz"
ADD "build/docker/${overlord_output_file}" "${server_dir}/bin/"
RUN ln -s "${instalog_dir}/cli.py" "/usr/bin/instalog"

# these files are likely to change often, put them at the end
ARG dome_builder_output_file="frontend.tar"
ADD "build/docker/${dome_builder_output_file}" "${dome_dir}/static/"

COPY py/umpire/docker/default_umpire.yaml \
  "${server_dir}/default_umpire.yaml"
COPY py "${server_dir}/py/"

CMD ["echo", "-e", \
     "\\n", \
     "You need to specify a command.\\n", \
     "\\n", \
     "Usage:\\n", \
     "  python manage.py migrate\\n", \
     "  uwsgi --ini uwsgi.ini\\n", \
     "  nginx -g 'daemon off;'\\n", \
     "  /usr/local/factory/bin/umpired\\n"]
