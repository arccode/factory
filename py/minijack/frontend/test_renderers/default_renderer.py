# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import itertools
from collections import defaultdict

from django.template import Context, loader

import minijack_common  # pylint: disable=W0611
from frontend import data
from frontend.test_renderers import RegisterTestRenderer


def IsInt(val):
  try:
    int(val)
  except ValueError:
    return False
  else:
    return True


def IsFloat(val):
  try:
    float(val)
  except ValueError:
    return False
  else:
    return True


def AllSame(vals):
  return all(x == vals[0] for x in vals)


def CalcFreqencyList(vals):
  vals = sorted(vals)
  frequency_list = sorted([(len(list(g)), k)
                           for k, g in itertools.groupby(vals)],
                          reverse=True)
  return frequency_list[:10]


def IsUsefulAttr(freq_list, orig_list):
  # We consider an attr useful if it's value are not empty, not all same,
  # and not too scattered (sum of top 10 < 25% total)
  return (len(freq_list) > 1 and
          sum(c for c, _ in freq_list) >= len(orig_list) * 0.25)


def GetIntStatistic(int_lists):
  int_stats = dict()
  for k, vals in int_lists.iteritems():
    v = CalcFreqencyList(vals)
    if IsUsefulAttr(v, vals):
      int_stats[k] = {
          'stats': data.GetStatistic(vals),
          'freq_list': v,
      }
  return sorted(int_stats.items())


def GetFloatStatistic(float_lists):
  return sorted((k, data.GetStatistic(vals))
                for k, vals in float_lists.iteritems()
                if not AllSame(vals))


def GetStrStatistic(str_lists):
  str_stats = dict()
  for k, vals in str_lists.iteritems():
    vals = [v for v in vals if v != '']
    v = CalcFreqencyList(vals)
    if IsUsefulAttr(v, vals):
      str_stats[k] = {
          'len': len(vals),
          'list': v,
      }
  return sorted(str_stats.items())


@RegisterTestRenderer('default')
def Render(event_attrs):
  all_lists = defaultdict(list)
  for e, attrs in event_attrs:
    for k, v in attrs.iteritems():
      all_lists[(e.event, k)].append(v)

  int_lists = dict()
  float_lists = dict()
  str_lists = dict()
  for k, l in all_lists.iteritems():
    if all(IsInt(val) for val in l):
      int_lists[k] = map(int, l)
    elif all(IsFloat(val) for val in l):
      float_lists[k] = map(float, l)
    else:
      str_lists[k] = l

  template = loader.get_template('test_renderers/default_renderer.html')
  context = Context({
      'int_stats': GetIntStatistic(int_lists),
      'float_stats': GetFloatStatistic(float_lists),
      'str_stats': GetStrStatistic(str_lists),
  })
  return template.render(context)
