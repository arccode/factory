# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This is the image for building Dome. There is another image for running Dome.
# The reason to separate them is because building requires much more
# dependencies. The dependencies are really big and we don't want to pull them
# all into the running image since they are useless after the build.

FROM node:6.9-slim
MAINTAINER Mao Huang <littlecvr@google.com>

# mixing ARG and ENV to make CMD able to use the variable, this technique is
# described here: https://docs.docker.com/engine/reference/builder/#arg
ARG workdir="/usr/src/app"
ENV workdir="${workdir}"

WORKDIR "${workdir}"

# copy package.json and pull in dependencies first, so we don't need to do this
# again if package.json hasn't been modified
COPY frontend/package.json "${workdir}/"
# npm outputs messages to stderr and docker makes them red, which is pretty
# scaring, redirect them to stdout
RUN npm install 2>&1
RUN npm dedupe 2>&1

# build
COPY frontend "${workdir}/"
RUN npm run build

# make sure others can read
RUN chmod 644 index.html bundle.js main.css

ARG output_file="frontend.tar"
ENV output_file="${output_file}"

RUN tar cvf "${output_file}" index.html bundle.js main.css

# nothing to do here
CMD ["echo"]
