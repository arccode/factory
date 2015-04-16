# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM ubuntu:trusty
MAINTAINER Wei-Ning Huang <wnhuang@google.com>

RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get install -y python-yaml python-netifaces python-pexpect \
	python-numpy python-twisted python-twisted-web python-protobuf \
	lighttpd python-flup unzip parallel pbzip2 pigz binutils sharutils \
	rsync aptitude screen vim psmisc dbus ssh htop openssh-server

RUN mkdir /var/run/sshd
RUN echo 'root:test0000' | chpasswd
RUN sed -i 's/PermitRootLogin without-password/PermitRootLogin yes/' \
	/etc/ssh/sshd_config

ENV NOTVISIBLE "in users profile"
RUN echo "export VISIBLE=now" >> /etc/profile

RUN rm -f /sbin/initctl
COPY fakeinitctl /sbin/initctl
COPY authorized_keys /root/.ssh/authorized_keys

EXPOSE 22 4455 9000 8082 8086
CMD ["/usr/sbin/sshd", "-D"]
