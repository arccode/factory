# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from datetime import datetime

from django.http import HttpResponse
from django.template import Context, loader

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.frontend.models import Device


DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'


def ToDatetime(datetime_str):
  if datetime_str:
    return datetime.strptime(datetime_str, DATETIME_FORMAT)
  else:
    return datetime_str


def GetBuildView(dummy_request):
  device_list = Device.objects.all().order_by('-latest_test_time')
  for device in device_list:
    device.goofy_init_time = ToDatetime(device.goofy_init_time)
    device.latest_test_time = ToDatetime(device.latest_test_time)

  template = loader.get_template('build_life.html')
  context = Context({
    'device_list': device_list,
  })
  return HttpResponse(template.render(context))
