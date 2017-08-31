// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.Plugin');

goog.require('goog.dom');

/**
 * Plugin object.
 *
 * @constructor
 * @param {!cros.factory.Goofy} goofy
 * @param {!Node} dom
 */
cros.factory.Plugin = function(goofy, dom) {
  this.goofy = goofy;
  this.dom = dom;
};

/**
 * Adds tooltip for a plugin element.
 * Because plugin UI is running in its own iframe, normal tooltip does not
 * work. This function provides a method to add tooltip to any elements in the
 * plugin DOM.
 *
 * @param {!HTMLElement} anchor
 * @param {!Node} content Dom object of the tooltip content.
 */
cros.factory.Plugin.prototype.addPluginTooltip = function(anchor, content) {
  const domHelper = goog.dom.getDomHelper(this.dom);
  const tooltip = new goog.ui.Tooltip(null, null, domHelper);
  tooltip.getElement().appendChild(content);

  goog.events.listen(anchor, goog.events.EventType.MOUSEOVER, () => {
    const position = new goog.positioning.AnchoredViewportPosition(
        anchor, goog.positioning.Corner.TOP_RIGHT, true);
    tooltip.showForElement(anchor, position);
  });
  goog.events.listen(anchor, goog.events.EventType.MOUSEOUT, () => {
    tooltip.detach();
    tooltip.setVisible(false);
  });
};
