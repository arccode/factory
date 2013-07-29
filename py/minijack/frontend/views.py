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

import factory_common  # pylint: disable=W0611
from cros.factory.minijack.frontend import data
from cros.factory.minijack.frontend.models import Device, Test, Component
from cros.factory.minijack.frontend.models import Event, Attr
from cros.factory.minijack.models import Device as MJDevice, Test as MJTest


DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'


def ToDatetime(datetime_str):
  if datetime_str:
    return datetime.strptime(datetime_str, DATETIME_FORMAT)
  else:
    return datetime_str


def DecodeFilterValue(k, val):
  if k.endswith('__in'):
    return val.split(',')
  else:
    return val


def BuildFilteredQuerySet(params, queryset):
  for k, v in params.iteritems():
    if k.endswith('__not'):
      k = k[:-5]
      queryset = queryset.exclude(**{k: DecodeFilterValue(k, v)})
    else:
      queryset = queryset.filter(**{k: DecodeFilterValue(k, v)})
  return queryset


def BuildFilterList(params, default):
  default = default or [False, '', '', '']
  result = []
  for k, v in params.iteritems():
    is_neg = False
    if k.endswith('__not'):
      k = k[:-5]
      is_neg = True
    result.append([is_neg] + k.split('__', 1) + [v])
  result = result or default
  return result


def GetDevicesView(request):
  get_params = request.GET.dict()
  filter_dict = dict((k, v) for k, v in get_params.iteritems() if '__' in k)

  device_list = BuildFilteredQuerySet(filter_dict, Device.objects).order_by(
      '-latest_test_time')
  # Filter out the none IP.
  for device in device_list:
    ips = [kv for kv in device.ips.split(', ') if not kv.endswith('=none')]
    device.ips = ', '.join(ips)

  filter_keys = sorted(MJDevice.GetFieldNames())
  default_filter = [[False, 'latest_test_time', 'lt',
                     datetime.now().strftime(DATETIME_FORMAT)[:10]]]
  enumerate_keys = dict()

  template = loader.get_template('devices_life.html')
  context = Context({
    'device_list': device_list,
    'get_params': get_params,
    'filter': {
      'enabled': bool(filter_dict),
      'keys': filter_keys,
      'list': BuildFilterList(filter_dict, default_filter),
      'enumerate_keys': enumerate_keys,
    },
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

  grouped_event = dict()
  for k, v in itertools.groupby(events, key=operator.attrgetter('log_id')):
    grouped_event[k] = [(e.event_id, e.event) for e in v]

  template = loader.get_template('device_life.html')
  context = Context({
    'device': device,
    'tests': tests,
    'comps': comps,
    'events': events,
    'stat': stat_dict,
    'grouped_event': grouped_event,
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
  get_params = request.GET.dict()
  filter_dict = dict((k, v) for k, v in get_params.iteritems() if '__' in k)

  order = request.GET.get('order', 'full_path')
  order_fn = GetGroupOrder(order)
  tests = BuildFilteredQuerySet(filter_dict, Test.objects).values(
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
    if failed_set:
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

  filter_keys = sorted(MJTest.GetFieldNames())
  default_filter = [[False, 'start_time', 'lt',
                     datetime.now().strftime(DATETIME_FORMAT)[:10]],
                    [False, 'factory_md5sum', 'exact', '']]
  enumerate_keys = dict()
  enumerate_keys['factory_md5sum'] = sorted(list(set(
      Test.objects.exclude(factory_md5sum='')
      .values_list('factory_md5sum', flat=True))))

  template = loader.get_template('tests_life.html')
  context = Context({
    'order': order,
    'test_stats': test_stats,
    'failed_devices': test_to_devices,
    'device_info': device_info,
    'get_params': get_params,
    'filter': {
      'enabled': bool(filter_dict),
      'keys': filter_keys,
      'list': BuildFilterList(filter_dict, default_filter),
      'enumerate_keys': enumerate_keys,
    },
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


def GetHwidsView(request):
  get_params = request.GET.dict()
  filter_dict = dict((k, v) for k, v in get_params.iteritems() if '__' in k)
  device_list = BuildFilteredQuerySet(filter_dict, Device.objects).exclude(
      hwid='').order_by('hwid')

  class_set = set(Component.objects.values_list('component_class', flat=True))

  hwid_to_devices = dict()
  for k, g in itertools.groupby(device_list, key=operator.attrgetter('hwid')):
    hwid_to_devices[k] = sorted([(d.device_id, d.serial, d.mlb_serial,
                                  d.latest_test_time) for d in g])

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

  filter_keys = sorted(MJDevice.GetFieldNames())
  default_filter = [[False, 'latest_test_time', 'lt',
                     datetime.now().strftime(DATETIME_FORMAT)[:10]]]
  enumerate_keys = dict()

  template = loader.get_template('hwids_life.html')
  context = Context({
    'hwid_list': hwid_names_pair,
    'class_set': class_set,
    'device_list': hwid_to_devices,
    'get_params': get_params,
    'filter': {
      'enabled': bool(filter_dict),
      'keys': filter_keys,
      'list': BuildFilterList(filter_dict, default_filter),
      'enumerate_keys': enumerate_keys,
    },
  })
  return HttpResponse(template.render(context))
