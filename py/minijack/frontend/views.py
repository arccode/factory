# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import operator
import itertools
from datetime import datetime

from django.http import HttpResponse
from django.template import Context, loader

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.frontend.models import Device, Test, Component
from cros.factory.minijack.frontend.models import Event, Attr


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


def GetDeviceView(dummy_request, device_id):
  device = Device.objects.get(device_id=device_id)
  tests = Test.objects.filter(device_id=device_id).order_by('-start_time')
  comps = Component.objects.filter(device_id=device_id).order_by('component')

  # Count the passed and failed tests.
  count_passed = len([t for t in tests if t.status == 'PASSED'])
  failed_tests = [t for t in tests if t.status == 'FAILED']
  count_failed = len(failed_tests)

  # Find the top failed tests.
  sorted_failed = sorted(failed_tests, key=operator.attrgetter('path'))
  grouped_failed = [(k, len(list(g))) for k, g in
                    itertools.groupby(sorted_failed,
                                      key=operator.attrgetter('path'))]
  top_failed = sorted(grouped_failed, key=operator.itemgetter(1), reverse=True)
  top_failed_list = [dict(path=p, count=c) for p, c in top_failed]

  stat_dict = {
    'cpassed': count_passed,
    'cfailed': count_failed,
    'ctotal': count_passed + count_failed,
    'top_failed': top_failed_list[:5],
  }

  template = loader.get_template('device_life.html')
  context = Context({
    'device': device,
    'tests': tests,
    'comps': comps,
    'stat': stat_dict,
  })
  return HttpResponse(template.render(context))


def GetEventView(dummy_request, event_id):
  event = Event.objects.get(event_id=event_id)
  attrs = Attr.objects.filter(event_id=event_id).order_by('attr')
  for attr in attrs:
    attr.value = attr.value.decode('string-escape')

  # Find the surrounding events.
  device_id = event.device_id
  events = Event.objects.filter(device_id=device_id).order_by('-time')
  for i in range(len(events)):
    if events[i].event_id == event_id:
      events_after = events[max(0, i - 5) : i]
      events_before = events[i + 1 : min(len(events), i + 6)]
      break
  else:
    events_after = events_before = []

  template = loader.get_template('event_life.html')
  context = Context({
    'event': event,
    'attrs': attrs,
    'events_before': events_before,
    'events_after': events_after,
  })
  return HttpResponse(template.render(context))
