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
ARG alpine_repository="http://dl-3.alpinelinux.org/alpine/edge/testing/"

# Create Umpire mount point. Normally we should mount this (and Docker will
# create it for us) when calling the run command, but that's not the case for
# unit tests. Not creating this directory may cause unit tests to fail.
RUN mkdir -p "${umpire_dir_in_dome}"

# Install packages. Python packages should be installed by pip if possible.
# However, uwsgi-python from pip needs to build from source, Twisted has
# package signing problem, so we will install them using apk.
#
#  pigz, py-pip, py-twisted, py-yaml, python, tar: Used by Umpire
#  (buzybox tar doesn't support -I, which is used in file_utils.ExtractFile)
#  gnupg, python-gnupg: Used by umpire/service/dkps and archiver
#  rsync: Used by umpire/service/rsync
#  jq: Will be used by umpire in future.
#
#  py-protobuf: Dependencies that are used by some board's shop_floor
#
#  nginx, uwsgi-python: Used by Dome.
#
#  apache2-utils, openssl: Used by Overlord setup.sh
#
#  util-linux: For GNU mount since busybox mount doesn't support offset.
#  coreutils: For GNU mktemp since busybox mktemp doesn't support --tmpdir.
RUN apk upgrade --no-cache && apk add --no-cache \
    apache2-utils \
    coreutils \
    gnupg \
    jq \
    nginx \
    openssl \
    pigz \
    py-pip \
    py-twisted \
    python \
    rsync \
    tar \
    unzip \
    util-linux \
    uwsgi-python \
  && apk add --no-cache --repository "${alpine_repository}" \
    lbzip2 \
  && ln -s /usr/bin/lbzip2 /usr/bin/pbzip2


# Prepare requirements file and install pip packages.
COPY py/dome/requirements.txt "${dome_dir}/"
COPY py/instalog/requirements.txt "${instalog_dir}/"
# TODO(hungte) Move Umpire packages to its own requirements file.
RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir \
      protobuf==3.2.0 \
      python-gnupg==0.4.0 \
      PyYAML==3.12 \
      -r "${dome_dir}/requirements.txt" \
      -r "${instalog_dir}/requirements.txt"

COPY py_pkg "${server_dir}/py_pkg/"
COPY bin "${server_dir}/bin/"

# add docker client -- do not install docker via apk -- it will try to install
# docker engine which takes a lot of space as well (we don't need it, we need
# only the small client to communicate with the host's docker server)
ADD build/docker/docker.tgz /

# these files are unlikely to change often, put them here to take advantage of
# docker's cache
COPY py/dome/uwsgi.ini py/dome/manage.py "${dome_dir}/"
COPY py/dome/nginx.conf /etc/nginx/nginx.conf

ARG overlord_output_file="overlord.tar.gz"
ADD "build/docker/${overlord_output_file}" "${server_dir}/bin/"
RUN ln -s "${instalog_dir}/cli.py" "/usr/bin/instalog"

# these files are likely to change often, put them at the end
ARG dome_builder_output_file="frontend.tar"
ADD "build/docker/${dome_builder_output_file}" "${dome_dir}/static/"

COPY py/umpire/docker/default_umpire.yaml \
  "${server_dir}/default_umpire.yaml"
COPY py "${server_dir}/py/"

COPY sh/cros_payload.sh "${server_dir}/sh/"

CMD ["echo", "-e", \
     "\\n", \
     "You need to specify a command.\\n", \
     "\\n", \
     "Usage:\\n", \
     "  python manage.py migrate\\n", \
     "  uwsgi --ini uwsgi.ini\\n", \
     "  nginx -g 'daemon off;'\\n", \
     "  /usr/local/factory/bin/umpired\\n"]
