# Copyright 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Argument handling for pytests.

To use this functionality, add the ARGS attribute to your pytest.  You can then
use the args attribute to access the attribute values.

  from cros.factory.utils.arg_utils import Arg
  class MyTest(unittest.TestCase):
    ARGS = [
      Arg('explode', bool, 'True if device is expected to explode'),
      Arg('countdown_secs', int, 'Number of seconds to wait for explosion', 0),
      Arg('title', str, 'Title in countdown window', default=None),
    ]

    def runTest(self):
      if self.args.title:
        self.ui.SetTitle(self.args.title)
      device.StartCountdown(self.args.countdown_secs)
      time.sleep(self.args.countdown_secs)
      self.assertEqual(self.args.explode, device.exploded)
"""

from .type_utils import Enum


# Save the 'type' function (since we'll be overloading it in Arg.__init__).
TYPE = type

# For unset default value, since we do want to specify None as default value.
_DEFAULT_NOT_SET = object()


class ArgError(ValueError):
  """Represents a problem with Arg specification or validation."""


class Arg:
  """The specification for a single test argument."""
  # pylint: disable=redefined-builtin

  def __init__(self, name, type, help,
               default=_DEFAULT_NOT_SET, _transform=None, schema=None):
    """Constructs a test argument.

    Args:

      name: Name of the argument. This will be the key in a ``dargs``
        dict in the test list.
      type: Type of the argument, or (if more than one type is permitted)
        a tuple of allowable types. If ``default`` is None, then None
        is also implicitly allowed. For example::

          type=int         # Allow only integers
          type=(int, str)  # Allow int or string

        You can also use an ``Enum`` object as a type.  First import
        it::

          from cros.factory.utils.type_utils import Enum

        Then in an ``Arg`` constructor, you can write::

          type=Enum(['CHARGE', 'DISCHARGE'])
              # Allow only the strings 'CHARGE' or 'DISCHARGE'

      help: A string describing how to use the argument. This will be
        included in the test catalog in the documentation bundle and
        may be formatted using `reStructuredText
        <http://docutils.sourceforge.net/docs/ref/rst/restructuredtext.html>`_.
      default: A default value for the argument. If there is no
        default value, this is omitted.
      _transform: A transform function to be applied to the value after the
        argument is resolved.
      schema: A utils.schema object for checking the argument.
    """
    if not name:
      raise ArgError('Argument is missing a name')
    if not type:
      raise ArgError('Argument %s is missing a type' % name)

    # Always make type a tuple.
    if not isinstance(type, tuple):
      type = (type,)
    if any(not isinstance(x, TYPE) and not isinstance(x, Enum)
           for x in type):
      raise ArgError('Argument %s has invalid types %r' % (name, type))

    if not help:
      raise ArgError('Argument %s is missing a help string' % name)

    # Allow None for all optional arguments with default None
    # Pylint has a false-negative here.  pylint: disable=unidiomatic-typecheck
    if default is None and (TYPE(None) not in type):
      type += (TYPE(None),)
    # pylint: enable=unidiomatic-typecheck

    self.name = name
    self.help = help
    self.type = type
    self.default = default
    self.transform = _transform
    self.schema = schema

    # Check validity of default.
    if self.IsOptional():
      if not self.ValueMatchesType(default):
        raise ArgError('Default value %s should have type %r, not %r' % (
            default, type, TYPE(default)))
      if self.schema:
        self.schema.Validate(default)

  def ValueMatchesType(self, value):
    """Returns True if value matches the type for this argument."""
    for t in self.type:
      if isinstance(t, TYPE) and isinstance(value, t):
        return True
      if isinstance(t, Enum) and value in t:
        return True
    return False

  def IsOptional(self):
    return self.default is not _DEFAULT_NOT_SET

  def AddToParser(self, parser):
    """Add itself to argparse.ArgumentParser.

    Args:
      parser: argparse.ArgumentParser object
    """
    if (len(self.type) >= 1 and self.type[0] not in [str, list, bool, int] and
        not isinstance(self.type[0], Enum)):
      raise ValueError('Arg %s cannot be transfered. %s' %
                       (self.name, self.type))

    if self.IsOptional():
      args = ['--' + self.name.replace('_', '-')]
    else:
      args = [self.name]

    kwargs = {
        'help': self.help,
        'default': self.default}
    if self.type[0] == bool:
      if self.default is True:
        args = ['--no-%s' % self.name.replace('_', '-')]
        kwargs['default'] = True
        kwargs['action'] = 'store_false'
      else:
        kwargs['default'] = False
        kwargs['action'] = 'store_true'
    elif self.type[0] == int:
      kwargs['type'] = int
    elif self.type[0] == list:
      kwargs['nargs'] = '*'
    elif isinstance(self.type[0], Enum):
      kwargs['type'] = str
      kwargs['choices'] = self.type[0]
    parser.add_argument(*args, **kwargs)


class Dargs:
  """A class to hold all the parsed arguments for a factory test."""

  def __init__(self, **kwargs):
    for key, value in kwargs.items():
      setattr(self, key, value)

  def ToDict(self):
    return {k: v for k, v in self.__dict__.items() if not k.startswith('__')}


class Args:
  """A class to hold a list of argument specs for an argument parser."""

  def __init__(self, *args):
    """Constructs an argument parser.

    Args:
      args: A list of Arg objects.
    """
    self.args = args

    if any(not isinstance(x, Arg) for x in args):
      raise TypeError('Arguments to Args object should all be Arg objects')

    # Throws an exception on duplicate arguments
    self.args_by_name = {x.name: x for x in args}

  def Parse(self, dargs, unresolvable_type=None):
    """Parses a dargs object from the test list.

    Args:
      dargs: A name/value map of arguments from the test list.
      unresolvable_type: A type indicates the arguments can not be resolved at
          compile time but may be resolved at runtime. We do not validate or
          transform unresolvable_type arguments.

    Returns:
      An object containing an attribute for each argument.
    """
    attributes = {}

    errors = []
    for arg in self.args:
      if arg.name not in dargs and not arg.IsOptional():
        errors.append('Required argument %s not specified' % arg.name)
        continue

      value = dargs.get(arg.name, arg.default)
      if not arg.ValueMatchesType(value):
        errors.append('Argument %s should have type %r, not %r' % (
            arg.name, arg.type, type(value)))
        errors.append('Argument %s=%r' % (arg.name, value))
        continue

      if not unresolvable_type or not isinstance(value, unresolvable_type):
        if arg.schema:
          try:
            arg.schema.Validate(value)
          except Exception as e:
            errors.append(repr(e))

        if arg.transform:
          value = arg.transform(value)

      attributes[arg.name] = value

    extra_args = sorted(set(dargs.keys()) - set(self.args_by_name.keys()))
    if extra_args:
      errors.append('Extra arguments %r' % extra_args)

    if errors:
      raise ArgError('; '.join(errors))

    return Dargs(**attributes)


def MergeArgs(old_args, new_args):
  """Merges two arg lists and overwrites with items from new_args on conflict.

  Args:
    old_args: the old arg list.
    new_args: the new arg list.

  Returns:
    A merged arg list.
  """
  args = list(old_args)
  for new_arg in new_args:
    found = False
    for i, element in enumerate(args):
      if element.name == new_arg.name:
        found = True
        args[i] = new_arg
        break
    if not found:
      args.append(new_arg)
  return args
