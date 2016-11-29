# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM alpine:3.4
MAINTAINER Mao Huang <littlecvr@google.com>

# need to explicitly assign PYTHONPATH for uwsgi
ENV PYTHONPATH="/usr/local/lib/python2.7/site-packages"

ARG dome_dir="/var/db/factory/dome"
ARG umpire_server_dir="/usr/local/factory"

# pigz, py-pip, py-twisted, py-yaml, python, lighttpd: Used by Umpire
# gnupg, python-gnupg: Used by umpire/service/archiver
# py-flup: Used by umpire/service/absub_logparser
# rsync: Used by umpire/service/rsync

# py-protobuf: Dependencies that are used by some board's shop_floor

# nginx, uwsgi-python: Used by Dome
# cannot install uwsgi using pip since we don't have compiler

# TODO(pihsun): Add pbzip2 when there's alpine package for it.
RUN apk upgrade --no-cache && apk add --no-cache \
  gnupg \
  lighttpd \
  nginx \
  pigz \
  py-flup \
  py-pip \
  py-twisted \
  py-yaml \
  python \
  rsync \
  unzip \
  uwsgi-python \
  && apk add --no-cache \
  --repository http://dl-3.alpinelinux.org/alpine/edge/testing/ \
  py-protobuf \
  && pip install \
  python-gnupg

COPY py_pkg "${umpire_server_dir}/py_pkg/"
COPY bin "${umpire_server_dir}/bin/"

# add docker client -- do not install docker via apk -- it will try to install
# docker engine which takes a lot of space as well (we don't need it, we need
# only the small client to communicate with the host's docker server)
ADD build/docker/docker.tgz /

# Use pre-built static cgpt, since there's no cgpt package in alpine.
ARG static_cgpt_path="build/docker/cgpt"
COPY "${static_cgpt_path}" /usr/local/bin/cgpt
RUN chmod 755 /usr/local/bin/cgpt

# these files are unlikely to change often, put them here to take advantage of
# docker's cache
COPY py/dome/nginx.conf /etc/nginx/nginx.conf
COPY py/dome/uwsgi.ini py/dome/manage.py py/dome/requirements.txt "${dome_dir}/"
RUN pip install --no-cache-dir -r "${dome_dir}/requirements.txt"

# these files are likely to change often, put them at the end
# TODO(pihsun): Move dome to the same location with umpire server, so we don't
#               need two duplicates of dome.
COPY py/dome/backend "${dome_dir}/backend/"
ARG builder_output_file="frontend.tar"
ADD "build/docker/${builder_output_file}" "${dome_dir}/frontend/"

COPY py/umpire/docker/default_umpire.yaml \
  "${umpire_server_dir}/default_umpire.yaml"
COPY py "${umpire_server_dir}/py/"

CMD ["echo", "-e", \
     "\\n", \
     "You need to specify a command.\\n", \
     "\\n", \
     "Usage:\\n", \
     "  python manage.py migrate\\n", \
     "  uwsgi --ini uwsgi.ini\\n", \
     "  nginx -g 'daemon off;'\\n", \
     "  /usr/local/factory/bin/umpired\\n"]
