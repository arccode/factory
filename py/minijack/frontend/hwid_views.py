# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import itertools
import operator

from django.http import HttpResponse
from django.template import Context, loader
from django.utils import simplejson

from cros.factory.minijack.frontend.models import Device, Component


def GetHwidView(dummy_request):
  device_list = Device.objects.exclude(hwid='').order_by('hwid')

  class_set = set(Component.objects.values_list('component_class', flat=True))

  hwid_to_devices = dict()
  for k, g in itertools.groupby(device_list, key=operator.attrgetter('hwid')):
    hwid_to_devices[k] = sorted([(d.device_id, d.serial, d.mlb_serial,
                                  d.latest_test_time) for d in g],
                                key=operator.itemgetter(1))

  hwid_names_pair = []
  # Get components for each HWID
  for k, g in hwid_to_devices.iteritems():
    id_list = map(operator.itemgetter(0), g)
    class_to_name = dict(Component.objects.filter(device_id__in=id_list)
                         .values_list('component_class', 'component_name'))
    name_list = []
    for c in class_set:
      name_list.append(class_to_name[c] if c in class_to_name else '')
    hwid_names_pair.append((k, name_list))

  template = loader.get_template('hwid_life.html')
  context = Context({
    'hwid_list': hwid_names_pair,
    'class_set': class_set,
    'device_list_json': simplejson.dumps(hwid_to_devices),
  })
  return HttpResponse(template.render(context))
