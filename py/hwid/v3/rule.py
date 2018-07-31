# Copyright 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Base classes of rule language implementation.

For metaclasses used to provide constructors and representers to the YAML
parser, please reference:

http://pyyaml.org/wiki/PyYAMLDocumentation#Constructorsrepresentersresolvers

for some examples.
"""

import collections
import functools
import logging
import re
import threading
import time

import factory_common  # pylint: disable=unused-import
from cros.factory.utils import type_utils


_rule_functions = {}


class RuleException(Exception):
  pass


class RuleLogger(object):
  """A logger for tracing the evaluation of rules.

  Attributes:
    info: Logs with INFO tag.
    warning: Logs with WARNING tag.
    error: Logs with ERROR tag.
  """
  VALID_TAGS = set(['info', 'warning', 'error'])
  LogEntry = collections.namedtuple('LogEntry', ['time_stamp', 'message'])

  def __init__(self):
    self.info = []
    self.warning = []
    self.error = []

  def Log(self, tag, message):
    """Log a message with the given tag with a timestamp.

    Args:
      tag: The tag of the given message. Must be one of ('info', 'warning',
          'error').
      message: A string indicating the message to log.
    """
    if tag not in RuleLogger.VALID_TAGS:
      raise RuleException('Invalid logging tag: %r' % tag)
    getattr(self, tag).append(RuleLogger.LogEntry(
        time.time(), '%s: %s' % (tag.upper(), message)))

  def Info(self, message):
    self.Log('info', message)

  def Warning(self, message):
    self.Log('warning', message)

  def Error(self, message):
    self.Log('error', message)

  def Dump(self):
    """Dumps the log in chronological order to a string."""
    logs = sorted(self.info + self.warning + self.error)
    return '\n' + '\n'.join([log.message for log in logs])

  def Reset(self):
    """Resets the logger by cleaning all the log messages."""
    self.info = []
    self.warning = []
    self.error = []


class Context(object):
  """A class for holding the context objects for evaluating rule functions.

  It converts its constructor's input key-value pairs to the object's
  attributes.
  """

  def __init__(self, **kwargs):
    for key, value in kwargs.iteritems():
      setattr(self, key, value)


# A thread-local object to hold the context object and a logger for rule
# evaluation.
_context = threading.local()
_context.value = None
_context.logger = RuleLogger()


def GetContext():
  """API to get the Context object."""
  return _context.value


def GetLogger():
  """API to get the RuleLogger object."""
  return _context.logger


def SetContext(context):
  """API to set the Context object. Logger should also be cleared."""
  if not isinstance(context, (type(None), Context)):
    raise RuleException('SetContext only accepts Context object')
  _context.value = context
  _context.logger.Reset()


def RuleFunction(ctx_list):
  """Decorator method to specify and check context for rule functions.

  It also registers the decorated rule function to the _rule_functions dict.
  The dict can then be used as the globals to evaluate Python expressions of
  rule functions.

  For example:

    @RuleFunction(['foo'])
    def RuleFunctionBar(...)
      ...

  This will do:
    1. Register 'RuleFunctionBar' to _rule_functions so it'll be parsed as a
       valid rule function.
    2. Before 'RuleFunctionBar' is evaluated, it'll check that the Context
       object has an attribute 'foo' in it.

  Args:
    ctx_list: A list of strings indicating the context that the rule function
        operates under. The Context object being loaded during the rule function
        evaluation must have these context attributes.

  Raises:
    ValueError if the Context object does not have all the required context
    attributes.
  """
  def Wrapped(fn):
    def RuleFunctionRepr(*args, **kwargs):
      """A method to dump a string to represent the rule function being called.
      """
      result = ''.join([
          '%s(' % fn.__name__,
          ', '.join(['%r' % arg for arg in args]),
          ', '.join(['%r=%r' % (key, value) for key, value in kwargs.items()]),
          ')'])
      return result

    @functools.wraps(fn)
    def ContextAwareFunction(*args, **kwargs):
      context = GetContext()
      for ctx in ctx_list:
        if not getattr(context, ctx, None):
          raise ValueError('%r not found in context' % ctx)
      result = fn(*args, **kwargs)
      # Log the rule function being evaluated and its result.
      GetLogger().Info('  %s: %r' % (RuleFunctionRepr(*args, **kwargs), result))
      return result

    if fn.__name__ in _rule_functions:
      raise KeyError('Re-defining rule function %r' % fn.__name__)
    _rule_functions[fn.__name__] = ContextAwareFunction
    return ContextAwareFunction
  return Wrapped


class Rule(object):
  """The Rule class.

  Rule objects should be called through the Evaluate method. Depending on the
  rule functions being called, proper Context objects could be needed to
  evaluate some Rule objects.

  Args:
    name: The name of this rule as a string.
    when: A Python expression as the execution condition of the rule. The
        expression should evaluate to True or False.
    evaluate: A list of Python expressions to evaluate if 'when' evalutes to
        True.
    otherwise: A list of Python expressions to evaluate if 'when' evaluates to
        False.
  """
  def __init__(self, name, evaluate, when=None, otherwise=None):
    if otherwise and not when:
      raise RuleException(
          "'when' must be specified along with 'otherwise' in %r" % name)

    self.name = name
    self.when = when
    self.evaluate = evaluate
    self.otherwise = otherwise

  def __eq__(self, rhs):
    return isinstance(rhs, Rule) and self.__dict__ == rhs.__dict__

  def __ne__(self, rhs):
    return not self == rhs

  @classmethod
  def CreateFromDict(cls, rule_dict):
    """Creates a Rule object from the given dict.

    The dict should look like:

      {
        'name': 'namespace.rule.name'
        'when': 'SomeRuleFunction(...)'
        'evaluate': [
            'RuleFunction1(...)',
            'RuleFunction2(...)'
        ]
        'otherwise': [
            'RuleFunction3(...)',
            'RuleFunction4(...)'
        ]
      }

    with 'when' and 'otherwise' being optional.
    """
    for field in ('name', 'evaluate'):
      if not rule_dict.get(field):
        raise RuleException('Required field %r not specified' % field)
    return Rule(rule_dict['name'], rule_dict['evaluate'],
                when=rule_dict.get('when'),
                otherwise=rule_dict.get('otherwise'))

  def ExportToDict(self):
    """Exports this rule to a dict.

    Returns:
      A dictionary which can be converted to an instance of Rule back by
      `CreateFromDict` method.
    """
    ret = {}
    ret['name'] = self.name
    ret['evaluate'] = self.evaluate
    if self.when is not None:
      ret['when'] = self.when
    if self.otherwise is not None:
      ret['otherwise'] = self.otherwise
    return ret

  def Validate(self):
    otherwise = (type_utils.MakeList(self.otherwise)
                 if self.otherwise is not None else [])
    for expr in (type_utils.MakeList(self.when) +
                 type_utils.MakeList(self.evaluate) + otherwise):
      try:
        _Eval(expr, {})
      except KeyError:
        continue

  def Evaluate(self, context):
    """Evalutes the Rule object.

    Args:
      context: A Context object.

    Raises:
      RuleException if evaluation fails.
    """
    logger = GetLogger()

    def EvaluateAllFunctions(function_list):
      for function in function_list:
        try:
          logger.Info('%s' % function)
          _Eval(function, {})
        except Exception as e:
          raise RuleException(
              'Evaluation of %r in rule %r failed: %r' %
              (function, self.name, e))
    try:
      SetContext(context)
      logger.Info('Checking rule %r' % self.name)
      if self.when is not None:
        logger.Info("Evaluating 'when':")
        logger.Info('%s' % self.when)
        if _Eval(self.when, {}):
          logger.Info("Evaluating 'evaluate':")
          EvaluateAllFunctions(type_utils.MakeList(self.evaluate))
        elif self.otherwise is not None:
          logger.Info("Evaluating 'otherwise':")
          EvaluateAllFunctions(type_utils.MakeList(self.otherwise))
      else:
        logger.Info("Evaluating 'evaluate':")
        EvaluateAllFunctions(type_utils.MakeList(self.evaluate))
    finally:
      if logger.error:
        raise RuleException(logger.Dump() +
                            '\nEvaluation of rule %r failed' % self.name)
      logging.debug(logger.Dump())
      SetContext(None)

  @classmethod
  def EvaluateOnce(cls, expr, context):
    """Evaluate the given expr under the given context once.

    Args:
      expr: A string of Python expression.
      context: A Context object.

    Returns:
      The retrun value of evaluation of expr.
    """
    logger = GetLogger()
    try:
      SetContext(context)
      return _Eval(expr, {})
    finally:
      if logger.error:
        raise RuleException(logger.Dump())
      logging.debug(logger.Dump())
      SetContext(None)


class Value(object):
  """A class to hold a value for expression evaluation.

  The value can be a plain string or a regular expression.

  Attributes:
    raw_value: A string of value or None.
    is_re: If True, raw_value is treated as a regular expression in expression
        evaluation.
  """
  def __init__(self, raw_value, is_re=False):
    self.raw_value = raw_value
    self.is_re = is_re

  def Matches(self, operand):
    """Matches the value of operand.

    The value to be matched depends on the type of operand. If it is Value,
    matches its 'raw_value'; otherwise, matches itself.

    The way to match operand depends on the instance's 'is_re' attribute. If
    'is_re' is True, it checks if the target matches the regular expression.
    Otherwise, a string comparison is used.

    Args:
      operand: The operand to match with.

    Returns:
      True if self matches operand, False otherwise.
    """
    if isinstance(operand, Value):
      if operand.is_re:
        # If operand is a regular expression Value object, compare with __eq__
        # directly.
        return self.__eq__(operand)
      operand = operand.raw_value
    if self.is_re:
      return re.match(self.raw_value, operand) is not None
    else:
      return self.raw_value == operand

  def __eq__(self, operand):
    return isinstance(operand, Value) and self.__dict__ == operand.__dict__

  def __ne__(self, operand):
    return not self == operand

  def __repr__(self):
    return '%s(%r, is_re=%r)' % (
        self.__class__.__name__, self.raw_value, self.is_re)


def _Eval(expr, local):
  # Lazy import to avoid circular import problems.
  # These imports are needed to make sure all the rule functions needed by
  # HWID-related operations are loaded and initialized.
  # pylint: disable=unused-import,unused-variable
  import cros.factory.hwid.v3.common_rule_functions
  import cros.factory.hwid.v3.hwid_rule_functions
  return eval(expr, _rule_functions, local)  # pylint: disable=eval-used
