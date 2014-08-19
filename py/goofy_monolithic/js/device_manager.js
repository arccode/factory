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
   * @type {cros.factory.Goofy}
   */
  this.goofy = goofy;

  /**
   * Map each path of device node to its children.
   * @type {Object}
   */
  this.mapToSubnode = {};

  /**
   * Map each path of device node to its hardware info.
   * @type {Object}
   */
  this.mapToDeviceData = {};

  /**
   * Map each path of device node to its name.
   * @type {Object}
   */
  this.mapToDescription = {};
}

/**
 * Recursively process data to data structure.
 * @param {Node} xmlData The overall parsed output of device data.
 * @param {string} nodePath Indicates XPath from root to the processing node.
 */
cros.factory.DeviceManager.prototype.processData = function(xmlData, nodePath) {

  var node = goog.dom.xml.selectSingleNode(xmlData, nodePath);
  var subnode = [];
  var deviceDataHtml = goog.dom.createDom('div');
  var deviceData = goog.dom.createDom('table', {'class': 'two-column-table'});

  for (var childNode = node.firstChild;
       childNode != null; childNode = childNode.nextSibling) {
    if (childNode.nodeName == 'description') {
      continue;
    }
    if (childNode.nodeName == 'html_string') {
      deviceDataHtml.innerHTML = childNode.textContent;
      continue;
    }

    if (childNode.nodeName == 'node') {
      subnode[subnode.length] = childNode;
    } else {
      var firstRow = goog.dom.createElement('tr');
      goog.dom.appendChild(
          firstRow,
          goog.dom.createDom('td', null, childNode.nodeName));

      if (!childNode.hasChildNodes) {
        continue;
      }

      for (var iterNode = childNode.firstChild;
           iterNode != null; iterNode = iterNode.nextSibling) {
        if (iterNode.nodeName == 'node') {
          continue;
        }

        var itemData = goog.dom.createElement('td');

        if (iterNode.textContent == '') {
          for (var j = 0; j < iterNode.attributes.length; j ++) {
            goog.dom.append(itemData, iterNode.attributes[j].value + ' ');
          }
        } else {
          goog.dom.append(itemData, iterNode.textContent);
        }

        if (iterNode == childNode.firstChild) {
          goog.dom.appendChild(firstRow, itemData);
          goog.dom.appendChild(deviceData, firstRow);
        } else {
          var otherRow = goog.dom.createElement('tr');
          goog.dom.appendChild(otherRow, goog.dom.createElement('td'));
          goog.dom.appendChild(otherRow, itemData);
          goog.dom.appendChild(deviceData, otherRow);
        }
      }
    }
  }

  if (node.nodeName == 'node') {
    this.mapToDescription[nodePath] = node.firstChild.textContent;
  } else {
    this.mapToDescription[nodePath] = node.nodeName;
  }
  goog.dom.appendChild(deviceDataHtml, deviceData);
  this.mapToDeviceData[nodePath] = deviceDataHtml;
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
        goog.dom.removeChildren(goog.dom.getElement('goofy-device-data-area'));
        goog.dom.append(
            /** @type {!Node} */(goog.dom.getElement('goofy-device-data-area')),
            goog.dom.createDom('div', {'class': 'device-name'}, this.mapToDescription[nodePath]));
        goog.dom.appendChild(
            goog.dom.getElement('goofy-device-data-area'),
            this.mapToDeviceData[nodePath]);
      }, false, this);

  for (var i = 0; i < this.mapToSubnode[nodePath].length; i ++) {
    var subnodePath = nodePath + '/node[@id=\'' + this.mapToSubnode[nodePath][i].id + '\']';
    this.createDrilldownMenu(itemMenuSubnode, subnodePath);
  }
}

/**
 * Call 'lshw' command and create the whole device manager.
 */
cros.factory.DeviceManager.prototype.getDeviceData = function() {

  goog.dom.removeChildren(goog.dom.getElement('goofy-device-data-area'));
  goog.dom.appendChild(
      goog.dom.getElement('goofy-device-data-area'),
      goog.dom.createDom(
          'div', {'class': 'device-manager-loading'},
          'Loading Device Manager...'));

  this.goofy.sendRpc(
      'GetDeviceInfo', [],
      function(data) {
        var itemMenu = new goog.ui.DrilldownRow({});
        itemMenu.decorate(goog.dom.getElement('tree-menu-root'));

        var xmlData = goog.dom.xml.loadXml(/** @type {string} */(JSON.parse(data)));
        this.deviceManager.processData(xmlData, '/list');
        this.deviceManager.createDrilldownMenu(itemMenu, '/list');

        goog.dom.removeChildren(goog.dom.getElement('goofy-device-data-area'));
      } );
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
      '<div id="goofy-device-data-area"></div>' +
      '<div id="goofy-device-list-area">' +
      '<table id="tree-menu-area">' +
      '<tr id="tree-menu-root"><td>Device Manager</td></tr></table></div>' +
      '<div id="goofy-device-manager-refresh"></div>' +
      goog.string.htmlEscape('') + '</div>');

  dialog.setButtonSet(goog.ui.Dialog.ButtonSet.createOk());
  dialog.setVisible(true);
  goog.dom.getElementByClass(
      'modal-dialog-title-text', dialog.getElement()).innerHTML = 'List hardware';

  var refreshButton = new goog.ui.Button(
      [goog.dom.createDom('div', {'id': 'goofy-device-manager-refresh-icon'}),
       goog.dom.createDom('div', {'id': 'goofy-device-manager-refresh-text'}, 'refresh')],
      goog.ui.FlatButtonRenderer.getInstance());

  refreshButton.render(goog.dom.getElement('goofy-device-manager-refresh'));

  this.getDeviceData();

  goog.events.listen(
      refreshButton,
      goog.ui.Component.EventType.ACTION,
      function() {
        this.mapToSubnode = {};
        this.mapToDeviceData = {};
        this.mapToDescription = {};

        var tree = document.getElementById('tree-menu-area');
        goog.dom.removeChildren(tree);
        tree.insertAdjacentHTML(
            'afterBegin',
            '<tr id="tree-menu-root"><td>Device Manager</td></tr>');

        this.getDeviceData();
      }, false, this);
}
