#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest
import yaml
import factory_common # pylint: disable=W0611

from cros.factory.rule import (
    RuleFunction, Rule, Value, Context, RuleException,
    SetContext, GetContext, GetLogger)


@RuleFunction(['string'])
def StrLen():
  return len(GetContext().string)

@RuleFunction(['string'])
def AssertStrLen(length):
  logger = GetLogger()
  if len(GetContext().string) <= length:
    logger.Error('Assertion error')


class HWIDRuleTest(unittest.TestCase):
  def setUp(self):
    self.context = Context(string='12345')

  def testRule(self):
    rule = Rule(name='foobar1',
                when='StrLen() > 3',
                evaluate='AssertStrLen(3)',
                otherwise=None)
    self.assertEquals(None, rule.Evaluate(self.context))
    rule = Rule(name='foobar2',
                when='StrLen() > 3',
                evaluate='AssertStrLen(6)',
                otherwise='AssertStrLen(8)')
    self.assertRaisesRegexp(
        RuleException, r"ERROR: Assertion error", rule.Evaluate, self.context)
    rule = Rule(name='foobar2',
                when='StrLen() > 6',
                evaluate='AssertStrLen(6)',
                otherwise='AssertStrLen(8)')
    self.assertRaisesRegexp(
        RuleException, r"ERROR: Assertion error", rule.Evaluate, self.context)


  def testValue(self):
    self.assertTrue(Value('foo').Matches('foo'))
    self.assertFalse(Value('foo').Matches('bar'))
    self.assertTrue(Value('^foo.*bar$', is_re=True).Matches('fooxyzbar'))
    self.assertFalse(Value('^foo.*bar$', is_re=True).Matches('barxyzfoo'))

  def testYAMLParsing(self):
    SetContext(self.context)
    self.assertRaisesRegexp(
        SyntaxError, r"unexpected EOF while parsing", yaml.load("""
            !rule
            name: foobar1
            when: StrLen() > 3
            evaluate: AssertStrLen(5
        """).Validate)
    self.assertRaisesRegexp(
        SyntaxError, r"invalid syntax \(<string>, line 1\)", yaml.load("""
            !rule
            name: foobar1
            when: StrLen( > 3
            evaluate: AssertStrLen(5)
        """).Validate)

    rule = yaml.load("""
        !rule
        name: foobar2
        when: StrLen() > 3
        evaluate: AssertStrLen(3)
    """)
    self.assertEquals(None, rule.Evaluate(self.context))

    rule = yaml.load("""
        !rule
        name: foobar2
        when: StrLen() > 3
        evaluate: AssertStrLen(6)
    """)
    self.assertRaisesRegexp(
        RuleException, r"ERROR: Assertion error", rule.Evaluate, self.context)

  def testEvaluateOnce(self):
    self.assertEquals(5, Rule.EvaluateOnce('StrLen()', self.context))
    self.assertRaisesRegexp(
        RuleException, r"ERROR: Assertion error",
        Rule.EvaluateOnce, 'AssertStrLen(6)', self.context)

if __name__ == '__main__':
  unittest.main()
