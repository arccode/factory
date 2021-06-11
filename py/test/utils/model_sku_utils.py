# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Boxster team suggests to import boxster data from model_sku.json."""

import logging
import os
import re

from cros.factory.gooftool import cros_config
from cros.factory.test.env import paths
from cros.factory.utils import config_utils


BOXSTER = 'boxster'
PROJECT_CONFIG_PATH = os.path.join(paths.FACTORY_DIR, 'project_config')
DEVICE_TREE_COMPATIBLE_PATH = cros_config.DEVICE_TREE_COMPATIBLE_PATH
PRODUCT_NAME_PATH = cros_config.PRODUCT_NAME_PATH
_RE_GENERATED_MODELSKU = re.compile(r'^(\w+)_(\w+)_model_sku$')
_PROGRAM = 'program'
_PROJECT = 'project'
_DESIGN = 'design'
_DEFAULT_SCHEMA_NAME = os.path.join(paths.FACTORY_DIR, 'py', 'test', 'pytests',
                                    'model_sku')


def GetDesignConfig(dut, product_name=None, sku_id=None,
                    default_config_dirs=None, config_name=BOXSTER,
                    schema_name=_DEFAULT_SCHEMA_NAME):
  """Use product_name and sku_id as key to find the right config in boxster.

  Args:
    product_name: The product_name of the device. If not specified, read from
      PRODUCT_NAME_PATH on x86 devices and DEVICE_TREE_COMPATIBLE_PATH on ARM
      devices.
    sku_id: The sku_id of the device. If not specified, read from
      cros_config.CrosConfig(dut=dut).GetSkuID().
    default_config_dirs: See config_utils.LoadConfig.
    config_name: Name of JSON config. If config_names is BOXSTER, searches
      config from PROJECT_CONFIG_PATH.
    schema_name: See config_utils.LoadConfig.
  """
  if product_name is None:
    try:
      product_names = [dut.ReadFile(PRODUCT_NAME_PATH).strip()]
    except Exception:
      product_names = dut.ReadFile(DEVICE_TREE_COMPATIBLE_PATH).split('\0')
  else:
    product_names = [product_name]

  # The config files are in the toolkit so we use os here.
  if config_name == BOXSTER:
    config_names = [
        os.path.splitext(config_path)[0]
        for config_path in os.listdir(PROJECT_CONFIG_PATH)
    ]
    default_config_dirs = PROJECT_CONFIG_PATH
    schema_name = _DEFAULT_SCHEMA_NAME
  else:
    config_names = [config_name]

  cros_config_object = cros_config.CrosConfig(dut=dut)
  if sku_id is None:
    sku_id = cros_config_object.GetSkuID()
  # json file must use str as key.
  if isinstance(sku_id, int):
    sku_id = str(sku_id)
  design = cros_config_object.GetModelName()

  matched_configs = []
  matched_design_config = {}
  # pylint: disable=redefined-argument-from-local
  for config_name in config_names:
    try:
      model_sku = config_utils.LoadConfig(
          default_config_dirs=default_config_dirs, config_name=config_name,
          schema_name=schema_name)
    except Exception:
      # Skip files that are not satisfied schema.
      logging.exception('%s is not valid.', config_name)
      continue

    sku_matched = False
    design_config = {}
    if 'product_sku' in model_sku:
      # pylint: disable=redefined-argument-from-local
      for product_name in product_names:
        try:
          design_config = model_sku['product_sku'][product_name][sku_id]
          sku_matched = True
          break
        except Exception:
          pass
    else:
      # TODO(chuntsen): Remove getting config from 'sku' after a period of time.
      try:
        design_config = model_sku['sku'][sku_id]
        sku_matched = True
      except Exception:
        pass

    try:
      design_common_config = model_sku['model'][design]
      design_matched = True
    except Exception:
      design_common_config = {}
      design_matched = False

    match = _RE_GENERATED_MODELSKU.match(os.path.basename(config_name))
    if match:
      design_config.setdefault(_PROGRAM, match.group(1))
      design_config.setdefault(_PROJECT, match.group(2))

    if sku_matched or design_matched:
      config_utils.OverrideConfig(design_common_config, design_config)
      matched_configs.append(config_name)
      matched_design_config = design_common_config

  if not matched_configs:
    logging.info(
        'There are no design config match for product_names: %r, sku_id: %s, '
        'config_names: %r.', product_names, sku_id, config_names)
  elif len(matched_configs) > 1:
    logging.info(
        'There are more than one design config matches for product_names: %r, '
        'sku_id: %s, config_names: %r, matched_configs: %r. The last is used.',
        product_names, sku_id, config_names, matched_configs)

  return matched_design_config
