# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM ubuntu:trusty
MAINTAINER Wei-Ning Huang <wnhuang@google.com>

ARG umpire_dir="/var/db/factory/umpire"

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

# From https://github.com/tianon/dockerfiles/tree/4d24a12b54b75b3e0904d8a285900d88d3326361/sbin-init/ubuntu/upstart/14.04
# Setup upstart envorinment
COPY setup/umpire_docker/init-fake.conf /etc/init/fake-container-events.conf
# Undo some leet hax of the base image
RUN rm /usr/sbin/policy-rc.d; \
        rm /sbin/initctl; dpkg-divert --rename --remove /sbin/initctl
# Generate a nice UTF-8 locale for our use
RUN locale-gen en_US.UTF-8 && update-locale LANG=en_US.UTF-8
# Remove some pointless services
RUN /usr/sbin/update-rc.d -f ondemand remove; \
        for f in \
                /etc/init/u*.conf \
                /etc/init/mounted-dev.conf \
                /etc/init/mounted-proc.conf \
                /etc/init/mounted-run.conf \
                /etc/init/mounted-tmp.conf \
                /etc/init/mounted-var.conf \
                /etc/init/hostname.conf \
                /etc/init/networking.conf \
                /etc/init/tty*.conf \
                /etc/init/plymouth*.conf \
                /etc/init/hwclock*.conf \
                /etc/init/module*.conf \
        ; do \
        dpkg-divert --local --rename --add "$f"; \
        done; \
        echo '# /lib/init/fstab: cleared out for bare-bones Docker' >/lib/init/fstab
# Let Upstart know it's in a container
ENV container docker

# TFTP Setting
RUN mkdir -p /root/tftpboot
RUN echo 'TFTP_USERNAME="tftp"' >/etc/default/tftpd-hpa
RUN echo 'TFTP_DIRECTORY="/root/tftpboot/"' >>/etc/default/tftpd-hpa
RUN echo 'TFTP_ADDRESS="0.0.0.0:69"' >>/etc/default/tftpd-hpa
RUN echo 'TFTP_OPTIONS="-v --secure"' >>/etc/default/tftpd-hpa

ARG board_default="default"
ARG umpire_server_dir="${umpire_dir}/${board_default}/toolkits/server/active/usr/local/factory"

COPY py "${umpire_server_dir}/py/"
COPY py_pkg "${umpire_server_dir}/py_pkg/"
COPY bin "${umpire_server_dir}/bin/"
COPY setup/umpire_docker/default_umpire.yaml "${umpire_dir}/${board_default}/active_umpire.yaml"
RUN "${umpire_server_dir}/bin/umpire" init --board="${board_default}"

# Pepare for takeoff
CMD ["/sbin/init"]
