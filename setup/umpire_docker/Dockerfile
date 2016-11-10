# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM ubuntu:trusty
MAINTAINER Wei-Ning Huang <wnhuang@google.com>

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
        python-yaml \
        python-netifaces \
        python-pexpect \
        python-numpy \
        python-twisted \
        python-twisted-web \
        python-protobuf \
        python-pyudev \
        python-pil \
        python-pymssql \
        python-flup \
        python-mysqldb \
        python-gnupg \
        binutils \
        cgpt \
        dbus \
        lighttpd \
        parallel \
        pbzip2 \
        pigz \
        psmisc \
        rsync \
        sharutils \
        tftpd-hpa \
        unzip

# TFTP Setting
RUN mkdir -p /root/tftpboot
RUN echo 'TFTP_USERNAME="tftp"' >/etc/default/tftpd-hpa
RUN echo 'TFTP_DIRECTORY="/root/tftpboot/"' >>/etc/default/tftpd-hpa
RUN echo 'TFTP_ADDRESS="0.0.0.0:69"' >>/etc/default/tftpd-hpa
RUN echo 'TFTP_OPTIONS="-v --secure"' >>/etc/default/tftpd-hpa

ARG umpire_dir="/var/db/factory/umpire"
ARG umpire_server_dir="/usr/local/factory"
ENV umpire_server_dir="${umpire_server_dir}"

COPY py "${umpire_server_dir}/py/"
COPY py_pkg "${umpire_server_dir}/py_pkg/"
COPY bin "${umpire_server_dir}/bin/"
COPY setup/umpire_docker/default_umpire.yaml \
  "${umpire_server_dir}/default_umpire.yaml"

# Pepare for takeoff
CMD "${umpire_server_dir}/bin/umpired"
