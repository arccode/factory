// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.Plugin');

goog.require('goog.dom');

/**
 * Plugin object.
 *
 * @constructor
 * @param {cros.factory.Goofy} goofy
 * @param {Node} dom
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
 * @param {Node} anchor
 * @param {Node} tooltip Dom object of the tooltip content.
 */
cros.factory.Plugin.prototype.addPluginTooltip = function(anchor, tooltip) {
  var tooltipContainer = goog.dom.createDom('div');
  goog.dom.classlist.add(tooltipContainer, 'goofy-plugin-tooltip');
  tooltipContainer.appendChild(tooltip);
  goog.events.listen(anchor, goog.events.EventType.MOUSEENTER, function() {
    var offsetLeft = anchor.offsetLeft + anchor.width;
    goog.style.setStyle(
        tooltipContainer,
        {'visibility': 'visible',
         'margin-left': offsetLeft});
  });
  goog.events.listen(anchor, goog.events.EventType.MOUSELEAVE, function() {
    goog.style.setStyle(
        tooltipContainer,
        {'visibility': 'hidden'});
  });
  goog.dom.appendChild(this.dom, tooltipContainer);
};
