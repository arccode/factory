# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM alpine:3.4
MAINTAINER Pin-Yen Lin <treapking@google.com>

ARG build_dir="/build"

ARG uftp_remote_url=\
"https://sourceforge.net/projects/uftp-multicast/files/source-tar/\
uftp-4.10.1.tar.gz"
ARG uftp_tarball="uftp-4.10.1.tar.gz"
ARG uftp_folder_name="uftp-4.10.1"

# curl, tar, build-base: Basic utils.
RUN apk upgrade --no-cache && apk add --no-cache \
  build-base \
  ca-certificates \
  linux-headers \
  tar \
  wget

RUN mkdir "${build_dir}"

RUN wget "${uftp_remote_url}"
RUN tar xf "${uftp_tarball}"
RUN make -C "${uftp_folder_name}" NO_ENCRYPTION=1
RUN cp "${uftp_folder_name}"/uftp "${build_dir}"
