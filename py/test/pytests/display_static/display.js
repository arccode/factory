// Copyright 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for display test.
 * @constructor
 * @param {string} container
 * @param {Array.<string>} colors
 */
var DisplayTest = function(container, colors) {
  this.container = container;
  this.display = false;
  this.focusItem = 0;
  this.styleDiv = null;
  this.fullScreenElement = null;
  this.allStyleList = [
    'display-subtest-solid-gray-170',
    'display-subtest-solid-gray-127',
    'display-subtest-solid-gray-63',
    'display-subtest-solid-red',
    'display-subtest-solid-green',
    'display-subtest-solid-blue',
    'display-subtest-solid-white',
    'display-subtest-solid-gray',
    'display-subtest-solid-black',
    'display-subtest-grid',
    'display-subtest-rectangle',
    'display-subtest-gradient-red',
    'display-subtest-gradient-green',
    'display-subtest-gradient-blue',
    'display-subtest-gradient-white',
    'display-subtest-image-complex',
    'display-subtest-image-black',
    'display-subtest-image-white',
    'display-subtest-image-crosstalk-black',
    'display-subtest-image-crosstalk-white',
    'display-subtest-image-gray-63',
    'display-subtest-image-gray-127',
    'display-subtest-image-gray-170',
    'display-subtest-image-horizontal-rgbw',
    'display-subtest-image-vertical-rgbw'
  ];
  var _ = cros.factory.i18n.translation;
  this.allItemList = [
    _('solid-gray-170'),
    _('solid-gray-127'),
    _('solid-gray-63'),
    _('solid-red'),
    _('solid-green'),
    _('solid-blue'),
    _('solid-white'),
    _('solid-gray'),
    _('solid-black'),
    _('grid'),
    _('rectangle'),
    _('gradient-red'),
    _('gradient-green'),
    _('gradient-blue'),
    _('gradient-white'),
    _('image-complex.bmp'),
    _('image-BLACK.BMP'),
    _('image-WHITE.BMP'),
    _('image-CrossTalk(black).bmp'),
    _('image-CrossTalk(white).bmp'),
    _('image-gray(63).bmp'),
    _('image-gray(127).bmp'),
    _('image-gray(170).bmp'),
    _('image-Horizontal(RGBW).bmp'),
    _('image-Vertical(RGBW).bmp')
  ];
  this.passed = _('Passed');
  this.failed = _('Failed');
  this.untested = _('Untested');
  this.instruct =
      _('Press Space to display;\n' +
        'After checking, Enter to pass; Esc to fail.');
  this.gridWidth = 10;
  this.gridHeight = 10;
  this.gridStyleCSS = '' +
      '.display-subtest-grid' +
      '{background-color: white; width: 100%; height: 100%; }' +
      '.display-subtest-grid-div' +
      '{background-color: black; width: ' + this.gridWidth + ';' +
      ' height: ' + this.gridHeight + ';' +
      ' border: 5px solid; }';
  this.itemList = [];
  this.styleList = [];
  //Puts the selected colors into itemList and styleList.
  for (var item = 0; item < colors.length; ++item) {
    var index = goog.array.findIndex(this.allItemList, function(ele) {
      return ele[cros.factory.i18n.DEFAULT_LOCALE] == colors[item];
    });
    if (index >= 0) {
      this.itemList.push(this.allItemList[index]);
      this.styleList.push(this.allStyleList[index]);
    }
  }
  this.itemNumber = this.itemList.length;
};

/**
 * Creates a display test and runs it.
 * @param {string} container
 * @param {Array.<string>} colors
 */
function setupDisplayTest(container, colors) {
  window.displayTest = new DisplayTest(container, colors);
  window.displayTest.init();
  window.displayTest.setupFullScreenElement();
  window.displayTest.setupGridStyle();
  window.displayTest.setupDisplayDiv();
  window.displayTest.setDisplayDivClass();
}

/**
 * Initializes display test ui.
 * There is a table with itemNumber rows and two columns.
 */
DisplayTest.prototype.init = function() {
  var caption = document.createElement('div');
  caption.className = 'display-caption';
  caption.appendChild(cros.factory.i18n.i18nLabelNode(this.instruct));
  $(this.container).appendChild(caption);

  var table = document.createElement('table');
  table.className = 'display-table';
  var tableBody = document.createElement('tbody');
  for (var item = 0; item < this.itemNumber; ++item) {
    var row = document.createElement('tr');

    var itemName = document.createElement('td');
    itemName.className = 'display-subtest-td';
    itemName.style.width = '50%';
    itemName.appendChild(cros.factory.i18n.i18nLabelNode(this.itemList[item]));
    row.appendChild(itemName);

    var itemStatus = document.createElement('td');
    itemStatus.id = 'item-' + item + '-status';
    itemStatus.itemName = this.itemList[item][cros.factory.i18n.DEFAULT_LOCALE];
    itemStatus.className = 'display-subtest-untested';
    itemStatus.appendChild(cros.factory.i18n.i18nLabelNode(this.untested));

    row.appendChild(itemStatus);
    tableBody.appendChild(row);
  }
  table.appendChild(tableBody);
  $(this.container).appendChild(table);
};

/**
 * Initializes fullscreen elements.
 */
DisplayTest.prototype.setupFullScreenElement = function() {
  this.fullScreenElement = document.createElement('div');
  this.fullScreenElement.className = 'display-full-screen-hide';
  $(this.container).appendChild(this.fullScreenElement);
};

/**
 * Initializes display style for fullscreen grid display.
 * Other display styles are set in display.css
 */
DisplayTest.prototype.setupGridStyle = function() {
  this.styleElement = document.createElement('style');
  this.styleElement.innerHTML = this.gridStyleCSS;
  this.fullScreenElement.appendChild(this.styleElement);
};

/**
 * Initializes display div in fullscreen element.
 */
DisplayTest.prototype.setupDisplayDiv = function() {
  this.displayDiv = document.createElement('div');
  this.displayDiv.id = 'display-div';
  this.fullScreenElement.appendChild(this.displayDiv);
  this.displayDiv.addEventListener('click', function(event) {
    window.test.sendTestEvent('OnSpacePressed', {});
  }.bind(this));
};

/**
 * Setups display div style. Grids need to be taking care of separately.
 */
DisplayTest.prototype.setDisplayDivClass = function() {
  var displayBeforeSetting = this.display;
  // cleans up display div
  this.displayDiv.innerHTML = '';
  this.displayDiv.className = this.styleList[this.focusItem];
  if (this.displayDiv.className == 'display-subtest-grid') {
    // Switches display on here so we can create grid
    // using correct width/height of display div when it is
    // in fullscreen. Uses displayBeforeSetting to restore display.
    this.switchDisplayOn();
    this.drawGrids();
    if (!displayBeforeSetting) {
      this.switchDisplayOff();
    }
  }
};

/**
 * Creates grids using table.
 */
DisplayTest.prototype.drawGrids = function() {
  var totalWidth = this.displayDiv.offsetWidth;
  var totalHeight = this.displayDiv.offsetHeight;
  var ySegments = Math.floor(totalHeight / this.gridHeight);
  var xSegments = Math.floor(totalWidth / this.gridWidth);
  var gridTable = document.createElement('table');
  gridTable.style.width = '100%';
  gridTable.style.height = '100%';
  var gridTableBody = document.createElement('tbody');
  for (var y = 0; y < ySegments; ++y) {
    var row = document.createElement('tr');
    for (var x = 0; x < xSegments; ++x) {
      var cell = document.createElement('td');
      var div = document.createElement('div');
      div.id = 'x-' + x + '-' + 'y-' + y;
      div.className = 'display-subtest-grid-div';
      cell.appendChild(div);
      row.appendChild(cell);
    }
    gridTableBody.appendChild(row);
  }
  gridTable.appendChild(gridTableBody);
  this.displayDiv.appendChild(gridTable);
};

/**
 * Toggles the fullscreen display visibility.
 */
DisplayTest.prototype.switchDisplayOnOff = function() {
  // If current display is on, turns it off
  if (this.display) {
    this.switchDisplayOff();
  } else {
    this.switchDisplayOn();
  }

};

/**
 * Switches the fullscreen display on. Sets fullScreenElement
 * visibility to visible and enlarges the test iframe to fullscreen.
 */
DisplayTest.prototype.switchDisplayOn = function() {
  this.display = true;
  this.fullScreenElement.className = 'display-full-screen-show';
  window.test.setFullScreen(true);
};

/**
 * Switches the fullscreen display off. Sets fullScreenElement
 * visibility to hidden and restores the test iframe to normal.
 */
DisplayTest.prototype.switchDisplayOff = function() {
  this.display = false;
  this.fullScreenElement.className = 'display-full-screen-hide';
  window.test.setFullScreen(false);
};


/**
 * Changes the status in test table based success or not.
 * Setups the display style for the next subtest.
 * Judges the whole test if there is no more subtests.
 * @param {boolean} success
 */
DisplayTest.prototype.judgeSubTest = function(success) {
  var id = 'item-' + this.focusItem + '-status';
  var element = document.getElementById(id);
  if (element) {
    element.innerHTML = '';
    if (success) {
      element.className = 'display-subtest-passed';
      element.appendChild(cros.factory.i18n.i18nLabelNode(this.passed));
    } else {
      element.className = 'display-subtest-failed';
      element.appendChild(cros.factory.i18n.i18nLabelNode(this.failed));
    }
    this.focusItem = this.focusItem + 1;
    if (this.focusItem < this.itemNumber) {
      window.displayTest.setDisplayDivClass();
    }
  }
  if (this.focusItem == this.itemNumber) {
    window.displayTest.judgeTest();
  }
};

/**
 * Checks if test is passed by checking the number of items that have passed.
 */
DisplayTest.prototype.judgeTest = function() {
  if (this.getClassArray('display-subtest-passed').length == this.itemNumber) {
    window.test.pass();
  } else {
    window.displayTest.failTest();
  }
};

/**
 * Fails the test and logs all the failed items.
 */
DisplayTest.prototype.failTest = function() {
  var failedItems = new Array();

  this.getClassArray('display-subtest-failed').forEach(
    function(element) {
      failedItems.push((element.itemName));
    }
  );

  this.failMsg = 'Display test failed. Malfunction items:';
  failedItems.forEach(function(element, index, array) {
    this.failMsg += ' ' + element;
    if (index != array.length - 1) {
      this.failMsg += ',';
    }
  }, this);
  window.test.fail(this.failMsg);
};

/**
 * Returns an Array coverted from the NodeList of the given class.
 * @param {string} className
 * @return {Array.<Element>}
 */
DisplayTest.prototype.getClassArray = function(className) {
  return Array.prototype.slice.call(document.getElementsByClassName(className));
};

/**
 * Switches the display.
 */
function switchDisplayOnOff() {
  window.displayTest.switchDisplayOnOff();
}

/**
 * Passes the subtest.
 */
function passSubTest() {
  window.displayTest.judgeSubTest(true);
}

/**
 * Fails the subtest.
 */
function failSubTest() {
  window.displayTest.judgeSubTest(false);
}

/**
 * Fails the test.
 */
function failTest() {
  window.displayTest.failTest();
}
