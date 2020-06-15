# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Instalog Event flow policy.

Decides whether or not a plugin should process an Event.
"""

import logging

# Name of the key used to specify the rule type in the config dictionary.
_RULE_TYPE_KEY = 'rule'

# Registry to store a NAME => CLASS mapping of all the possible rules.
_rule_registry = {}


class FlowPolicy:
  """A flow policy defines a set of allow and deny rules for Events.

  An event *must* match one of the allow rules, and not match *any* of the
  deny rules in order to match.
  """

  def __init__(self, allow=None, deny=None):
    """Constructor.

    Args:
      allow: A list of dicts, where each dict must contain the key
            _RULE_TYPE_KEY ('rule').  The value of 'rule' corresponds to a Rule
            class's NAME member.  Other key-values are used as arguments for
            the particular rule in use.
      deny: See allow.
    """
    self.allow = [Rule.FromDict(dct) for dct in allow or []]
    self.deny = [Rule.FromDict(dct) for dct in deny or []]

  def MatchEvent(self, event):
    """Checks an Event against allow and deny rules."""
    allow = False
    for rule in self.allow:
      allow = allow or rule.MatchEvent(event)
    deny = False
    for rule in self.deny:
      deny = deny or rule.MatchEvent(event)
    return allow and not deny

  def __repr__(self):
    """Implements repr function for debugging."""
    return ('FlowPolicy(allow=%r, deny=%r)'
            % (self.allow, self.deny))


class RuleMeta(type):
  """Metaclass to collect FlowRule classes into a class registry."""

  def __new__(cls, name, bases, class_dict):
    """Called when a class is defined."""
    mcs = type.__new__(cls, name, bases, class_dict)
    if hasattr(mcs, 'NAME'):
      if mcs.NAME in _rule_registry:
        raise RuntimeError('Multiple serializable classes with name "%s"'
                           % mcs.__name__)
      _rule_registry[mcs.NAME] = mcs
    return mcs


class Rule(metaclass=RuleMeta):
  """Superclass for rules which may or may not match an Event.

  Subclasses should define the constants NAME, KEYS, as well as the
  function MatchEvent.

  Properties:
    NAME: Defines the name of this rule.
    KEYS: Defines the names of arguments which may be provided to this rule.
          All arguments are optional.
  """

  def __init__(self, **kwargs):
    """Collects arguments into `args' member."""
    self.args = {}
    for key in self.KEYS:
      # All arguments are optional.  Ignore any missing ones.
      if key in kwargs:
        # Currently only the '==' operator is supported.
        self.args[key] = RHSOperation(kwargs.pop(key))
    if kwargs:
      raise ValueError('Extra arguments: %s' % kwargs)

  def __repr__(self):
    """Implements repr function for debugging."""
    return '%s(%r)' % (self.__class__.__name__, self.args)

  def __eq__(self, other):
    """Implements == operator."""
    return self.args == other.args

  @classmethod
  def FromDict(cls, dct):
    """Creates a rule from a configuration dict."""
    if _RULE_TYPE_KEY not in dct:
      raise ValueError('FlowPolicy: No `rule\' key found to specify rule type')
    rule_name = dct.pop(_RULE_TYPE_KEY)
    if rule_name not in _rule_registry:
      raise ValueError('FlowPolicy: No rule called `%s\'' % rule_name)
    return _rule_registry[rule_name](**dct)

  def MatchEvent(self, event):
    """Checks whether the provided event matches this rule."""
    raise NotImplementedError


class AllRule(Rule):
  """Allows any event."""

  NAME = 'all'
  KEYS = []

  def MatchEvent(self, event):
    """Checks whether the provided event matches this rule."""
    return True


class HistoryRule(Rule):
  """Checks for a particular entry in the Event's history."""

  NAME = 'history'
  KEYS = ['node_id', 'time', 'plugin_id',
          'plugin_type', 'target', 'position']

  def MatchEvent(self, event):
    """Checks whether the provided event matches this rule."""
    for position, process_stage in enumerate(event.history):
      logging.debug('%s: %r', position, process_stage)

      valid = True
      for key, operation in self.args.items():
        # Special case for the 'position' key.
        if key == 'position':
          lhs = position
          # If the specified position is negative, we need to
          # check against the negated index.
          if operation.rhs < 0:
            lhs -= len(event.history)
        else:
          lhs = getattr(process_stage, key)

        # Apply the operation to check the lhs.
        logging.debug('Checking %s %s...', lhs, operation)
        valid = valid and operation.Apply(lhs)
        if not valid:
          logging.debug('Short-circuit break')
          break

      if valid:
        logging.debug('Checked all arguments, matches')
        return True

    logging.debug('All history stages failed, no match')
    return False


class TestlogRule(Rule):
  """Checks for a particular entry in the Testlog Event."""
  # TODO(chuntsen): After we add the control feature of buffer plugin, we can
  #                 remove this TestlogRule.

  NAME = 'testlog'
  KEYS = ['type']

  def MatchEvent(self, event):
    """Checks whether the provided event matches this rule."""
    for key, operation in self.args.items():
      lhs = event.get(key, None)
      if not lhs:
        logging.debug('The %s is not in the event', key)
        return False

      # Apply the operation to check the lhs.
      logging.debug('Checking %s %s...', lhs, operation)
      if not operation.Apply(lhs):
        return False

    return True


class RHSOperation:
  """Represents an operator and a right-hand operand.

  Currently, the only supported operation is equality (==).
  """

  def __init__(self, rhs):
    """Constructor."""
    self.rhs = rhs

  def Apply(self, lhs):
    """Takes a right-hand operand and applies the operation."""
    return lhs == self.rhs

  def __repr__(self):
    """Implements repr function for debugging."""
    return 'RHSOperation(== %r)' % self.rhs

  def __eq__(self, other):
    """Implements == operator."""
    return self.rhs == other.rhs
