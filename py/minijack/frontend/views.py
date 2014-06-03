# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import copy
import operator
import itertools
from datetime import datetime

from django.shortcuts import render
from django.http import HttpResponse

import minijack_common  # pylint: disable=W0611
from models import Device, Test, Component, Event, Attr
from db import Database
from frontend import test_renderers, data

import settings


if not settings.IS_APPENGINE:
  import subprocess
  import tempfile


DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'


def DecodeFilterValue(model, k, val):
  field_name = k.rsplit('__')[0]
  if k.endswith('__in'):
    return [model.GetFieldObject(field_name).ToPython(v)
            for v in val.split(',')]
  else:
    return model.GetFieldObject(field_name).ToPython(val)


def BuildFilteredQuerySet(params, queryset):
  for k, v in params.iteritems():
    if k.endswith('__not'):
      k = k[:-5]
      queryset = queryset.Exclude(
          **{k: DecodeFilterValue(queryset.GetModel(), k, v)})
    else:
      queryset = queryset.Filter(
          **{k: DecodeFilterValue(queryset.GetModel(), k, v)})
  return queryset


def BuildFilterList(params, default=None):
  result = []
  for k, v in params.iteritems():
    is_neg = False
    if k.endswith('__not'):
      k = k[:-5]
      is_neg = True
    result.append([is_neg] + k.split('__', 1) + [v])
  result = result or default or [[False, '', '', '']]
  return result


def GetDeviceFilterContext(unused_database, filter_dict):
  default_filter = [[False, 'latest_test_time', 'lt',
                     datetime.now().strftime(DATETIME_FORMAT)[:10]]]
  return {
    'enabled': bool(filter_dict),
    'keys': sorted(Device.GetFieldNames()),
    'list': BuildFilterList(filter_dict, default_filter),
    'enumerate_keys': dict(),
  }


def GetTestFilterContext(database, filter_dict):
  default_filter = [[False, 'start_time', 'lt',
                     datetime.now().strftime(DATETIME_FORMAT)[:10]],
                    [False, 'factory_md5sum', 'exact', '']]
  enumerate_keys = dict()
  enumerate_keys['factory_md5sum'] = sorted(list(
      database(Test).Exclude(factory_md5sum='')
      .ValuesList('factory_md5sum', distinct=True)))
  return {
    'enabled': bool(filter_dict),
    'keys': sorted(Test.GetFieldNames()),
    'list': BuildFilterList(filter_dict, default_filter),
    'enumerate_keys': enumerate_keys,
  }


def GetDevicesView(request):
  database = Database.Connect()
  get_params = request.GET.dict()
  filter_dict = dict((k, v) for k, v in get_params.iteritems() if '__' in k)

  device_list = BuildFilteredQuerySet(filter_dict, database(Device)).GetAll()
  # Filter out the none IP.
  for device in device_list:
    ips = [kv for kv in device.ips.split(', ') if not kv.endswith('=none')]
    device.ips = ', '.join(ips)
  context = {
    'device_list': device_list,
    'filter': GetDeviceFilterContext(database, filter_dict),
  }
  return render(request, 'devices_life.html', context)


def GetDeviceView(request, device_id):
  database = Database.Connect()
  device = database(Device).Filter(device_id=device_id).GetOne()
  tests = database(Test).Filter(device_id=device_id).OrderBy(
      '-start_time').GetAll()
  comps = database(Component).Filter(device_id=device_id).GetAll()
  events = database(Event).Filter(device_id=device_id).OrderBy(
      'log_id', 'time').GetAll()
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

  context = {
    'device': device,
    'tests': tests,
    'comps': comps,
    'events': events,
    'stat': stat_dict,
    'grouped_event': grouped_event,
  }
  return render(request, 'device_life.html', context)


def GetEventView(request, event_id):
  database = Database.Connect()
  event = database(Event).Filter(event_id=event_id).GetOne()
  attrs = database.GetRelated(Attr, event)
  attrs = sorted(attrs, key=operator.attrgetter('attr'))
  for attr in attrs:
    attr.value = attr.value.decode('string-escape')

  # Find the surrounding events.
  device_id = event.device_id
  events = database(Event).Filter(device_id=device_id).GetAll()
  events = sorted(events, key=operator.attrgetter('time'), reverse=True)
  for i in range(len(events)):
    if events[i].event_id == event_id:
      events_after = events[max(0, i - 5) : i]
      events_before = events[i + 1 : min(len(events), i + 6)]
      break
  else:
    events_after = events_before = []

  context = {
    'event': event,
    'attrs': attrs,
    'events_before': events_before,
    'events_after': events_after,
  }
  return render(request, 'event_life.html', context)


def GetGroupOrder(order):
  if order == 'pytest_name':
    return operator.itemgetter('pytest_name')
  elif order == 'short_path':
    return (lambda x: x['path'].rsplit('.', 1)[-1])
  else:
    return operator.itemgetter('path')


def GetTestsView(request):
  database = Database.Connect()
  get_params = request.GET.dict()
  filter_dict = dict((k, v) for k, v in get_params.iteritems() if '__' in k)

  order = request.GET.get('order', 'full_path')
  order_fn = GetGroupOrder(order)
  tests = BuildFilteredQuerySet(filter_dict, database(Test)).Values(
      'status', 'duration', 'end_time', 'path', 'device_id',
      'pytest_name').GetAll()
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

    # TODO(pihsun): Can do statistics in BigQuery.
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
                     database(Device).IterFilterIn('device_id', all_failed_set))

  context = {
    'order': order,
    'test_stats': test_stats,
    'failed_devices': test_to_devices,
    'device_info': device_info,
    'filter': GetTestFilterContext(database, filter_dict),
  }
  return render(request, 'tests_life.html', context)


def GetScreenshotImage(unused_request, ip_address):
  if settings.IS_APPENGINE:
    return HttpResponse(
        "Screenshot feature is disabled on App Engine" +
        " (can't create subprocess)")
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
  database = Database.Connect()
  get_params = request.GET.dict()
  filter_dict = dict((k, v) for k, v in get_params.iteritems() if '__' in k)

  device_list = BuildFilteredQuerySet(filter_dict, database(Device)).Exclude(
      hwid='').OrderBy('hwid').GetAll()

  class_set = set(database(Component).ValuesList(
      'component_class', distinct=True).GetAll())
  hwid_to_devices = dict()
  for k, g in itertools.groupby(device_list, key=operator.attrgetter('hwid')):
    hwid_to_devices[k] = sorted([(d.device_id, d.serial, d.mlb_serial,
                                  d.latest_test_time) for d in g])

  hwid_names_pair = []
  # Get components for each HWID
  for k, g in hwid_to_devices.iteritems():
    id_list = [v[0] for v in g]
    class_to_name = dict((c.component_class, c.component_name) for c in
                         database(Component).IterFilterIn('device_id', id_list))
    name_list = []
    for c in class_set:
      name_list.append(class_to_name[c] if c in class_to_name else '')
    hwid_names_pair.append((k, name_list))

  context = {
    'hwid_list': hwid_names_pair,
    'class_set': class_set,
    'device_list': hwid_to_devices,
    'filter': GetDeviceFilterContext(database, filter_dict),
  }
  return render(request, 'hwids_life.html', context)


def BuildTestQuerySet(database, test_type, name, order):
  Q = database.Q

  queryset = database(Test)
  if test_type == 'pytest_name':
    queryset.Filter(pytest_name=name)
  elif test_type == 'short_path':
    queryset.Filter(Q(path=name) | Q(path__endswith='.'+name))
  else:
    queryset.Filter(path=name)
  if order == 'last_passed':
    # Last passed test per device
    queryset.Filter(status='PASSED')

  if order != 'all':
    last_tests = copy.deepcopy(queryset).Values('device_id').Annotate(
        max_end_time=('max', 'end_time'))
    queryset.Join(last_tests, device_id='device_id', end_time='max_end_time')

  return queryset


def GetTestView(request):
  database = Database.Connect()
  get_params = request.GET.dict()
  filter_dict = dict((k, v) for k, v in get_params.iteritems() if '__' in k)

  test_type = request.GET.get('type', 'full_path')
  name = request.GET.get('name', '')
  order = request.GET.get('order', 'last')

  tests = BuildTestQuerySet(database, test_type, name, order)

  filtered_tests = BuildFilteredQuerySet(filter_dict, tests)
  test_list = filtered_tests.Values('invocation', 'event_id').GetAll()
  invocation_list = [t['invocation'] for t in test_list]
  event_id_list = [t['event_id'] for t in test_list]

  events = (list(database(Event).IterFilterIn('log_id', invocation_list)) +
            list(database(Event).IterFilterIn('event_id', event_id_list)))

  all_attrs = sorted(list(database.GetRelated(Attr, events)),
      key=operator.attrgetter('event_id'))
  event_id_dict = dict((e.event_id, e) for e in events)
  event_attr_list = []
  for e, g in itertools.groupby(all_attrs, key=operator.attrgetter('event_id')):
    event_attr_list.append(
        (event_id_dict[e], dict((a.attr, a.value) for a in g)))

  __import__('frontend.test_renderers', fromlist=['*'])
  all_renderer = test_renderers.GetRegisteredRenderers()

  renderer_name = name.rsplit('.', 1)[-1]
  if not renderer_name in all_renderer:
    renderer_name = 'default'
  rendered_result = all_renderer[renderer_name](event_attr_list)

  context = {
    'get_params': get_params,
    'test_name': name,
    'filter': GetTestFilterContext(database, filter_dict),
    'rendered_result': rendered_result,
  }
  return render(request, 'test_life.html', context)

