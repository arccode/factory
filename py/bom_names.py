# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""HWID data web service ; pool of names for use during bulk HWID creation."""


def process_bom_names(s):
  """Return a list of HWID names, filtered for legality and upper-cased."""
  name_list = s.split()
  name_list = [x.upper() for x in name_list if len(x) <= 8 and x.isalpha()]
  return set(name_list)


BOM_NAME_SET = process_bom_names("""
Sweetgum
Cashew
Mango
Sumac
Lacquer
Holly
Alder
Birch
Hazel
Dogwood
Acacia
Chestnut
Beech
Oak
Boojum
Hickory
Walnut
Laurel
Baobab
Balsa
Durian
Cacao
Linden
Mahogany
Fig
Mulberry
Eucalypt
Myrtle
Guava
Tupelo
Ash
Olive
Hawthorn
Apple
Pear
Rowan
Citrus
Cherry
Poplar
Aspen
Willow
Maple
Lychee
Elm
Teak
Palm
Bamboo
Nutmeg
Cypress
Juniper
Redwood
Sequoia
Fir
Cedar
Larch
Spruce
Pine
Rimu
Totara
Miro
Yew
Ginkgo
""")
