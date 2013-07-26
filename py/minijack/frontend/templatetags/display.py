# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from django import template
from django.utils import simplejson
from django.utils.safestring import mark_safe


register = template.Library()


@register.filter
def DisplayFloat(value):
  if isinstance(value, float) or isinstance(value, int):
    return "%.2f" % value
  else:
    return value

@register.filter
def Jsonify(value):
  return mark_safe(simplejson.dumps(value))
