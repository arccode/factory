#!/usr/bin/env python2
"""Test program for tiny_par_unittest.py."""


from __future__ import print_function

import sys


def main():
  if len(sys.argv) > 2:
    print(' '.join(sys.argv[2:]))
  if len(sys.argv) > 1:
    sys.exit(int(sys.argv[1]))


if __name__ == '__main__':
  main()
