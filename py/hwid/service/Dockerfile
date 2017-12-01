# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

FROM python:2.7.13-alpine

ARG workdir="/usr/src/app"
ARG cros_src_dir="${workdir}/cros/src"
ARG chromeos_hwid_dir="${cros_src_dir}/platform/chromeos-hwid"
ARG regions_dir="${cros_src_dir}/platform2/regions"
ARG factory_dir="${cros_src_dir}/platform/factory"
ARG hwid_service_dir="${factory_dir}/py/hwid/service"
WORKDIR "${workdir}"

# The build context should be in the CROS src dir.
ADD platform/chromeos-hwid "${chromeos_hwid_dir}"
ADD platform2/regions "${regions_dir}"
ADD platform/factory/py "${factory_dir}/py"
ADD platform/factory/py_pkg "${factory_dir}/py_pkg"

RUN apk upgrade --no-cache && \
    apk add --no-cache py-pip && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r "${hwid_service_dir}/requirements.txt"

ENV CROS_WORKON_SRCROOT "${workdir}/cros"
ENV RPC_SERVER "${hwid_service_dir}/rpc_server.py"

CMD python ${RPC_SERVER}
