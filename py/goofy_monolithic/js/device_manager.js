// Copyright 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.DeviceManager');

goog.require('goog.debug');
goog.require('goog.dom');
goog.require('goog.dom.xml');
goog.require('goog.events');
goog.require('goog.string');
goog.require('goog.ui.Button');
goog.require('goog.ui.Component');
goog.require('goog.ui.Dialog');
goog.require('goog.ui.Dialog.ButtonSet');
goog.require('goog.ui.DrilldownRow');
goog.require('goog.ui.FlatButtonRenderer');

/** @constructor */
cros.factory.DeviceManager = function(goofy) {

  /**
   * @type {cros.factory.goofy}
   */
  this.goofy = goofy;

  /**
   * Map each path of device node to its children.
   * @type {Map}
   */
  this.mapToSubnode = {};

  /**
   * Map each path of device node to its hardware info.
   * @type {Map}
   */
  this.mapToDeviceData = {};

  /**
   * Map each path of device node to its name.
   * @type {Map}
   */
  this.mapToDescription = {};
}

/**
 * Recursively process data to data structure.
 * @param {goog.dom.xml} xmlData The overall parsed output of device data.
 * @param {string} nodePath Indicates XPath from root to the processing node.
 */
cros.factory.DeviceManager.prototype.processData = function(xmlData, nodePath) {

  var node = goog.dom.xml.selectSingleNode(xmlData, nodePath);
  var subnode = [];
  var deviceData = '';

  for (var childNode = node.firstChild;
       childNode != null; childNode = childNode.nextSibling) {
    if (childNode.nodeName == 'node') {
      subnode[subnode.length] = childNode;
    } else {
      deviceData = deviceData + childNode.nodeName + ':\n';

      if (!childNode.hasChildNodes)
        continue;

      for (var iterNode = childNode.firstChild;
           iterNode != null; iterNode = iterNode.nextSibling) {
        if (iterNode.nodeName == 'node') {
          continue;
        }

        deviceData = deviceData + '\t';
        if (iterNode.textContent == '') {
          for (var j = 0; j < iterNode.attributes.length; j ++) {
            deviceData = deviceData + iterNode.attributes[j].value + ' ';
          }
        } else {
          deviceData = deviceData + iterNode.textContent;
        }
        deviceData = deviceData + '\n';
      }
    }
  }

  this.mapToDescription[nodePath] = node.firstChild.textContent;
  this.mapToDeviceData[nodePath] = deviceData;
  this.mapToSubnode[nodePath] = subnode;

  for (var i = 0; i < subnode.length; i ++) {
    var subnodePath = nodePath + '/node[@id=\'' + subnode[i].id + '\']';
    this.processData(xmlData, subnodePath);
  }
}

/**
 * Recursively create a drilldown menu for each item of hardware list.
 * @param {goog.ui.DrilldownRow} itemMenuParent The parent node to be attached.
 * @param {string} nodePath Indicates XPath from root to the processing node.
 */
cros.factory.DeviceManager.prototype.createDrilldownMenu = function(itemMenuParent, nodePath) {

  var itemMenuSubnode = new goog.ui.DrilldownRow(
      {html: '<tr><td><div id="show-button-' + nodePath +
             '" style="display:inline-table"></div></td></tr>'});
  itemMenuParent.addChild(itemMenuSubnode, true);

  var showButton = new goog.ui.Button(
      this.mapToDescription[nodePath], goog.ui.FlatButtonRenderer.getInstance());
  showButton.render(document.getElementById('show-button-' + nodePath));

  goog.events.listen(
      showButton,
      goog.ui.Component.EventType.ACTION,
      function() {
        goog.dom.setTextContent(
            goog.dom.getElementByClass('goofy-device-manager-area'),
            this.mapToDeviceData[nodePath]);
      }, false, this);

  for (var i = 0; i < this.mapToSubnode[nodePath].length; i ++) {
    var subnodePath = nodePath + '/node[@id=\'' + this.mapToSubnode[nodePath][i].id + '\']';
    this.createDrilldownMenu(itemMenuSubnode, subnodePath);
  }
}


/**
 * Create a new dialog to display the hardware lister.
 */
cros.factory.DeviceManager.prototype.showWindow = function() {

  var dialog = new goog.ui.Dialog();
  this.goofy.registerDialog(dialog);
  dialog.setModal(false);

  var viewSize = goog.dom.getViewportSize(goog.dom.getWindow(document) || window);
  var maxWidth = viewSize.width * cros.factory.MAX_DIALOG_SIZE_FRACTION;
  var maxHeight = viewSize.height * cros.factory.MAX_DIALOG_SIZE_FRACTION;

  dialog.setContent(
      '<div class="goofy-log-data"' +
      'style="width: ' + maxWidth + '; height: ' + maxHeight + '">' +
      '<div class="goofy-device-manager-area"></div>' +
      '<table id="tree-menu-area">' +
      '<tr id="tree-menu-root"><td>list</td></tr></table>' +
      goog.string.htmlEscape('') + '</div>');

  dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
  dialog.setVisible(true);
  goog.dom.getElementByClass(
      'modal-dialog-title-text', dialog.getElement()).innerHTML = 'list hardware';

  this.goofy.sendRpc(
      'GetLshwXml', [],
      function(data) {
        var tree = document.getElementById('tree-menu-root');
        var itemMenu = new goog.ui.DrilldownRow({});
        itemMenu.decorate(tree);

        var xmlData = goog.dom.xml.loadXml(JSON.parse(data));
        this.deviceManager.processData(xmlData, '/list/node');
        this.deviceManager.createDrilldownMenu(itemMenu, '/list/node');
      } );
}
