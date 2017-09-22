// Copyright 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

goog.provide('cros.factory.DeviceManager');

goog.require('goog.dom');
goog.require('goog.dom.xml');
goog.require('goog.events');
goog.require('goog.ui.Button');
goog.require('goog.ui.Component');
goog.require('goog.ui.Dialog');
goog.require('goog.ui.Dialog.ButtonSet');
goog.require('goog.ui.DrilldownRow');
goog.require('goog.ui.FlatButtonRenderer');

/**
 * @constructor
 * @param {cros.factory.Goofy} goofy
 */
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
   * Map each path of device node to its device info.
   * @type {Object}
   */
  this.mapToDeviceData = {};

  /**
   * Map each path of device node to its name.
   * @type {Object}
   */
  this.mapToDescription = {};

  /**
   * The full path name of a device node is stored here if its data is not
   * loaded yet.
   * @type {Array}
   */
  this.slowCommandsFullPath = [];

  /**
   * The corresponding function name in backend of a device node is stored here
   * if its data is not loaded yet. Backend (goofy_rpc.py) should assign
   * attribute 'slow_command' to the function name in the backend to collect
   * device info in the second round (non-blocking UI).
   * @type {Array}
   */
  this.slowCommandsBackendFunction = [];
};

/**
 * Recursively process data to data structure.
 * @param {Node} xmlData The overall parsed output of device data.
 * @param {string} nodePath Indicates the XPath from root according to xmlData
 *     to current processing device node.
 * @param {string} fullPath Indicates the XPath from root to current processing
 *     device, used to identify each node.
 */
cros.factory.DeviceManager.prototype.processData = function(
    xmlData, nodePath, fullPath) {

  var node = goog.dom.xml.selectSingleNode(xmlData, nodePath);

  if (node.nodeName == 'node') {
    this.mapToDescription[fullPath] = node.firstChild.textContent;
  } else {
    this.mapToDescription[fullPath] = node.nodeName;
  }

  if (node.getAttribute('slow_command') != null) {
    this.mapToDeviceData[fullPath] = goog.dom.createDom('div');
    goog.dom.append(
        this.mapToDeviceData[fullPath], goog.dom.createTextNode('Loading...'));
    this.mapToSubnode[fullPath] = [];

    this.slowCommandsFullPath[this.slowCommandsFullPath.length] = fullPath;
    this.slowCommandsBackendFunction[this.slowCommandsBackendFunction.length] =
        node.getAttribute('slow_command');

    return;
  }

  var subnode = [];
  var deviceDataHtml = goog.dom.createDom('div');
  var deviceDataTable = goog.dom.createDom('table', 'two-column-table');

  for (var childNode = node.firstChild; childNode != null;
       childNode = childNode.nextSibling) {
    if (childNode.nodeName == 'description') {
      continue;
    }
    if (childNode.nodeName == 'html_string') {
      deviceDataHtml.innerHTML = childNode.textContent;
      continue;
    }
    if (childNode.nodeName == 'node') {
      subnode[subnode.length] = childNode;
      continue;
    }

    var firstRow = goog.dom.createElement('tr');
    goog.dom.appendChild(
        firstRow, goog.dom.createDom('td', null, childNode.nodeName));

    if (!childNode.hasChildNodes) {
      continue;
    }

    for (var iterNode = childNode.firstChild; iterNode != null;
         iterNode = iterNode.nextSibling) {
      if (iterNode.nodeName == 'node') {
        continue;
      }

      var itemData = goog.dom.createElement('td');

      if (iterNode.textContent == '') {
        for (var j = 0; j < iterNode.attributes.length; j++) {
          goog.dom.append(itemData, iterNode.attributes[j].value + ' ');
        }
      } else {
        goog.dom.append(itemData, iterNode.textContent);
      }

      if (iterNode == childNode.firstChild) {
        goog.dom.appendChild(firstRow, itemData);
        goog.dom.appendChild(deviceDataTable, firstRow);
      } else {
        var otherRow = goog.dom.createElement('tr');
        goog.dom.appendChild(otherRow, goog.dom.createElement('td'));
        goog.dom.appendChild(otherRow, itemData);
        goog.dom.appendChild(deviceDataTable, otherRow);
      }
    }
  }

  goog.dom.appendChild(deviceDataHtml, deviceDataTable);
  this.mapToDeviceData[fullPath] = deviceDataHtml;
  this.mapToSubnode[fullPath] = subnode;

  for (var i = 0; i < subnode.length; i++) {
    var childNodePath = nodePath + '/node[@id=\'' + subnode[i].id + '\']';
    var childFullPath = fullPath + '/node[@id=\'' + subnode[i].id + '\']';
    this.processData(xmlData, childNodePath, childFullPath);
  }
};

/**
 * Creates a button of the device node in the menu to show its data.
 * @param {string} fullPath Indicates the XPath from root to current processing
 *     device, used to identify each node.
 */
cros.factory.DeviceManager.prototype.createButton = function(fullPath) {

  var showButton = new goog.ui.Button(
      this.mapToDescription[fullPath],
      goog.ui.FlatButtonRenderer.getInstance());
  showButton.render(document.getElementById('show-button-' + fullPath));

  if (fullPath == '/list') {
    return;
  }

  goog.events.listen(
      showButton, goog.ui.Component.EventType.ACTION, function() {
        goog.dom.removeChildren(goog.dom.getElement('goofy-device-data-area'));
        goog.dom.append(
            /** @type {!Node} */ (
                goog.dom.getElement('goofy-device-data-area')),
            goog.dom.createDom(
                'div', 'device-name', this.mapToDescription[fullPath]));
        goog.dom.appendChild(
            goog.dom.getElement('goofy-device-data-area'),
            this.mapToDeviceData[fullPath]);
      }, false, this);
};

/**
 * Recursively creates a drilldown menu for each item of device manager.
 * @param {goog.ui.DrilldownRow} itemMenuParent The parent node to be attached.
 * @param {string} fullPath Indicates the XPath from root to current processing
 *     device, used to identify each node.
 */
cros.factory.DeviceManager.prototype.createDrilldownMenu = function(
    itemMenuParent, fullPath) {

  var itemMenuSubnode = new goog.ui.DrilldownRow({
    html: goog.html.SafeHtml.create(
        'tr', {},
        goog.html.SafeHtml.create('td', {}, goog.html.SafeHtml.create('div', {
          'id': 'show-button-' + fullPath,
          'style': {'display': 'inline-table'}
        })))
  });
  itemMenuParent.addChild(itemMenuSubnode, true);

  this.createButton(fullPath);

  for (var i = 0; i < this.mapToSubnode[fullPath].length; i++) {
    this.createDrilldownMenu(
        itemMenuSubnode,
        fullPath + '/node[@id=\'' + this.mapToSubnode[fullPath][i].id + '\']');
  }
};

/**
 * Initializes the drilldown menu area and creates the list.
 */
cros.factory.DeviceManager.prototype.makeMenu = function() {

  var tree = goog.dom.getElement('tree-menu-area');
  goog.dom.removeChildren(tree);
  tree.insertAdjacentHTML(
      'afterBegin', '<tr id="tree-menu-root"><td>Device Manager</td></tr>');

  var itemMenu = new goog.ui.DrilldownRow({});
  itemMenu.decorate(goog.dom.getElement('tree-menu-root'));

  this.createDrilldownMenu(itemMenu, '/list');
};

/**
 * Gets device info from backend and creates the whole device manager.
 */
cros.factory.DeviceManager.prototype.getDeviceData = function() {

  goog.dom.removeChildren(goog.dom.getElement('goofy-device-data-area'));
  goog.dom.removeChildren(goog.dom.getElement('tree-menu-area'));
  goog.dom.appendChild(
      goog.dom.getElement('goofy-device-data-area'),
      goog.dom.createDom(
          'div', 'device-manager-loading', 'Loading Device Manager...'));

  // Executes general commands and ignores slower ones in first stage.
  this.goofy.sendRpcToPlugin('device_manager', 'GetDeviceInfo')
      .then((data) => {
        this.processData(
            goog.dom.xml.loadXml(data), '/list', '/list');
        this.makeMenu();
        goog.dom.removeChildren(goog.dom.getElement('goofy-device-data-area'));

        // Executes slower commands in second stage.
        this.goofy
            .sendRpcToPlugin(
                'device_manager', 'GetDeviceInfo',
                JSON.stringify(this.slowCommandsBackendFunction))
            .then((data) => {
              var parsedData = JSON.parse(data);

              for (var i = 0; i < parsedData.length; i++) {
                this.processData(
                    goog.dom.xml.loadXml(parsedData[i]), '/node',
                    this.slowCommandsFullPath[i]);
              }

              goog.dom.removeChildren(
                  goog.dom.getElement('goofy-device-data-area'));
              this.makeMenu();
            });
      });
};

/**
 * Creates a new dialog to display the device manager.
 */
cros.factory.DeviceManager.prototype.showWindow = function() {
  var content = goog.html.SafeHtml.create('div', {}, [
    goog.html.SafeHtml.create('div', {'id': 'goofy-device-data-area'}),
    goog.html.SafeHtml.create(
        'div', {'id': 'goofy-device-list-area'},
        goog.html.SafeHtml.create('table', {'id': 'tree-menu-area'})),
    goog.html.SafeHtml.create('div', {'id': 'goofy-device-manager-refresh'})
  ]);
  var dialog = this.goofy.createSimpleDialog('Device Manager', content);
  dialog.getElement().classList.add('goofy-device-manager');
  dialog.setVisible(true);

  var refreshButton = new goog.ui.Button(
      [
        goog.dom.createDom('div', {'id': 'goofy-device-manager-refresh-icon'}),
        goog.dom.createDom(
            'div', {'id': 'goofy-device-manager-refresh-text'}, 'refresh')
      ],
      goog.ui.FlatButtonRenderer.getInstance());
  refreshButton.render(goog.dom.getElement('goofy-device-manager-refresh'));

  this.getDeviceData();

  goog.events.listen(
      refreshButton, goog.ui.Component.EventType.ACTION, function() {
        this.mapToSubnode = {};
        this.mapToDeviceData = {};
        this.mapToDescription = {};

        this.getDeviceData();
      }, false, this);
};
