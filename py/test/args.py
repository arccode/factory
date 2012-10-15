# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


'''Argument handling for pytests.

To use this functionality, add the ARGS attribute to your pytest.  You can then
use the args attribute to access the attribute values.

  from cros.factory.test.args import Arg
  class MyTest(unittest.TestCase):
    ARGS = [
      Arg('explode', bool, 'True if device is expected to explode'),
      Arg('countdown_secs', int, 'Number of seconds to wait for explosion', 0),
      Arg('title', str, 'Title in countdown window', optional=True),
    ]

    def runTest(self):
      if self.args.title:
        self.ui.SetTitle(self.args.title)
      device.StartCountdown(self.args.countdown_secs)
      time.sleep(self.args.countdown_secs)
      self.assertEquals(self.args.explode, device.exploded)
'''


# Save the 'type' function (since we'll be overloading it in Arg.__init__).
TYPE = type


class Arg(object):
  # pylint: disable=W0622
  def __init__(self, name, type, help, default=None, optional=False):
    '''Constructor.

    Args:
      name: Name of the argument.
      type: Type of the argument, or a tuple of allowable types.  None is
        always allowed if optional is True.
      help: A help string.
      default: A default value for the argument.
      optional: Whether the argument is optional.
    '''
    if not name:
      raise ValueError('Argument is missing a name')
    if not type:
      raise ValueError('Argument %s is missing a type' % name)

    # Always make type a tuple.
    if not isinstance(type, tuple):
      type = (type,)
    if any(not isinstance(x, TYPE) for x in type):
      raise ValueError('Argument %s has invalid types %r' % (name, type))

    # Allow None for all optional arguments without defaults.
    if optional and (default is None) and (None not in type):
      type += (TYPE(None),)

    # Check type of default.
    if default and (not any(isinstance(default, t) for t in type)):
      raise ValueError('Default value %s should have type %r, not %r' % (
                       default, type, TYPE(default)))

    if not help:
      raise ValueError('Argument %s is missing a help string' % name)

    if default is not None:
      optional = True

    self.name = name
    self.help = help
    self.type = type
    self.default = default
    self.optional = optional


class Args(object):
  def __init__(self, *args):
    '''Constructs an argument parser.

    Args:
      args: A list of Arg objects.
    '''
    self.args = args

    if any(not isinstance(x, Arg) for x in args):
      raise TypeError('Arguments to Args object should all be Arg objects')

    # Throws an exception on duplicate arguments
    self.args_by_name = dict((x.name, x) for x in args)

  def Parse(self, dargs):
    '''Parses a dargs object from the test list.

    Args:
      dargs: A name/value map of arguments from the test list.

    Returns:
      An object containing an attribute for each argument.
    '''
    attributes = {}

    errors = []
    for arg in self.args:
      value = dargs.get(arg.name)
      if arg.name not in dargs:
        if not arg.optional:
          errors.append('Required argument %s not specified' % arg.name)
          continue
        if arg.default is not None:
          value = arg.default

      if (arg.name in dargs and
          not any(isinstance(value, t) for t in arg.type)):
        errors.append('Argument %s should have type %r, not %r' % (
            arg.name, arg.type, type(value)))
        continue

      attributes[arg.name] = value

    extra_args = sorted(set(dargs.keys()) - set(self.args_by_name.keys()))
    if extra_args:
      errors.append('Extra arguments %r' % extra_args)

    if errors:
      raise ValueError('; '.join(errors))

    return type('Dargs', (), attributes)
