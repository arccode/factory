# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM python:2.7

ARG workdir="/usr/src/"
ARG gcloud_archive_name="google-cloud-sdk-245.0.0-linux-x86_64.tar.gz"

ADD factory/py/hwid/service/appengine/requirements.txt \
  "${workdir}"/requirements.txt

RUN cd "${workdir}" && \
  wget "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/${gcloud_archive_name}" && \
  tar xvf "${gcloud_archive_name}" && \
  google-cloud-sdk/install.sh \
      --rc-path /root/.bashrc \
      --additional-components app-engine-python app-engine-python-extras \
      --quiet && \
  rm "${gcloud_archive_name}" && \
  pip install \
      --target "${workdir}"/lib \
      --requirement "${workdir}"/requirements.txt \
      mox==0.5.3 \
      mock==2.0.0 \
      protorpc-standalone==0.9.1 \
      PyYaml==3.11 \
      webapp2==3.0.0b1 \
      WebTest==2.0.29

ADD factory/py "${workdir}/cros/factory/py"
ADD factory/py_pkg "${workdir}/cros/factory/py_pkg"
ADD chromeos-hwid/py "${workdir}/cros/chromeos-hwid/py"
ADD factory/build/hwid/protobuf_out "${workdir}/protobuf_out"

ENV PYTHONPATH="${workdir}/lib:"\
"${workdir}/google-cloud-sdk/platform/google_appengine:"\
"${workdir}/protobuf_out"

CMD bash
