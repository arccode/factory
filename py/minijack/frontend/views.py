# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import itertools
import operator
import subprocess
import tempfile
from datetime import datetime

from django.http import HttpResponse
from django.template import Context, loader
from django.utils import simplejson

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.frontend import data
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
  # Filter out the none IP.
  for device in device_list:
    ips = [kv for kv in device.ips.split(', ') if not kv.endswith('=none')]
    device.ips = ', '.join(ips)

  template = loader.get_template('build_life.html')
  context = Context({
    'device_list': device_list,
  })
  return HttpResponse(template.render(context))


def GetDeviceView(dummy_request, device_id):
  device = Device.objects.get(device_id=device_id)
  tests = Test.objects.filter(device_id=device_id).order_by('-start_time')
  comps = Component.objects.filter(device_id=device_id).order_by(
      'component_class')
  events = Event.objects.filter(device_id=device_id).order_by('log_id', 'time')

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
    'events': events,
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


def GetGroupOrder(order):
  if order == 'pytest_name':
    return operator.itemgetter('pytest_name')
  elif order == 'short_path':
    return (lambda x: x['path'].rsplit('.', 1)[-1])
  else:
    return operator.itemgetter('path')


def GetTestsView(request):
  order = request.GET.get('order', 'full_path')
  order_fn = GetGroupOrder(order)
  tests = Test.objects.exclude(path='').values(
      'status', 'duration', 'end_time', 'path', 'device_id', 'pytest_name')

  tests = sorted(tests, key=order_fn)

  test_stats = []
  test_to_devices = dict()
  all_failed_set = set()
  for k, g in itertools.groupby(tests, key=order_fn):
    test_list = list(g)

    # only count devices that always fail on this test
    failed_set = (set(t['device_id'] for t in test_list
                      if t['status'] == 'FAILED') -
                  set(t['device_id'] for t in test_list
                      if t['status'] == 'PASSED'))
    test_to_devices[k] = sorted(list(failed_set))
    all_failed_set |= failed_set

    # Filter out nonexist duration data.
    duration_list = [float(t['duration']) for t in test_list
                     if float(t['duration']) != 0.0]

    duration_stats = data.GetStatistic(duration_list)

    try_list = [len(list(g)) for _, g in
                itertools.groupby(test_list,
                                  key=operator.itemgetter('device_id'))]
    try_stats = data.GetStatistic(try_list)

    num_test = len(test_list)
    num_pass = len([x for x in test_list if x['status'] == 'PASSED'])
    num_fail = len([x for x in test_list if x['status'] == 'FAILED'])

    test_stats.append({
      'path': k,
      'num_test': num_test,
      'latest_time': max(x['end_time'] for x in test_list),
      'duration_stats': duration_stats,
      'try_stats': try_stats,
      'pass_rate': num_pass / float(num_test),
      'fail_rate': num_fail / float(num_test),
    })
  device_info = dict((d.device_id,
                      (d.serial, d.mlb_serial, d.latest_test_time)) for d in
                     Device.objects.filter(device_id__in=all_failed_set))

  template = loader.get_template('tests_life.html')
  context = Context({
    'order': order,
    'test_stats': test_stats,
    'failed_devices_json': simplejson.dumps(test_to_devices),
    'device_info_json': simplejson.dumps(device_info),
  })
  return HttpResponse(template.render(context))


def GetScreenshotImage(dummy_request, ip_address):
  remote_url = 'root@' + ip_address
  remote_filename = '/tmp/screenshot.png'
  capture_cmd = (
    'DISPLAY=:0 XAUTHORITY=/home/chronos/.Xauthority '
    'import -window root -display :0 -screen ' + remote_filename)
  rc = subprocess.call(['ssh', remote_url, capture_cmd])

  # Check if ssh returns an error.
  if rc != 0:
    return HttpResponse(
      'Failed to ssh ' + ip_address + ', returned ' + str(rc) + '.')
  else:
    with tempfile.NamedTemporaryFile() as f:
      subprocess.call(['scp', remote_url + ':' + remote_filename, f.name])
      image_content = open(f.name, 'rb').read()
    # Remove remote image file.
    rm_cmd = 'rm ' + remote_filename
    subprocess.call(['ssh', remote_url, rm_cmd])
    return HttpResponse(image_content, content_type='image/png')
