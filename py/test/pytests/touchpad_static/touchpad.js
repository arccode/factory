// Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for touchpad test.
 * @constructor
 * @param {string} container
 * @param {int} xSegments
 * @param {int} ySegments
 * @param {int} countTarget
 */
TouchpadTest = function(container, xSegments, ySegments, countTarget) {
  this.container = container;
  this.xSegments = xSegments;
  this.ySegments = ySegments;
  this.leftCount = 0;
  this.rightCount = 0;
  this.countTarget = countTarget;

};

/**
 * Creates a touchpad test and runs it.
 * @param {string} container
 * @param {int} xSegments
 * @param {int} ySegments
 * @param {int} countTarget
 */
function setupTouchpadTest(container, xSegments, ySegments, countTarget) {
  window.touchpadTest = new TouchpadTest(container, xSegments, ySegments,
                                         countTarget);
  window.touchpadTest.init();
}

/**
 * Initializes touchpad div elements for touch and scroll.
 * The div contains a table with one row and two columns.
 * The first td contains a touch table, and the second td contains
 * a scroll table.
 * The touch table contains xSegment by ySegment divs
 * The scroll table contains 1 by ySegment divs
 * Also initialize the content in click table, which is built in html.
 */
TouchpadTest.prototype.init = function() {
  var table = document.createElement("table");
  var tableBody = document.createElement("tbody");
  table.style.width = "100%";
  table.style.height = "100%";
  var row = document.createElement("tr");

  var touchTableCell = document.createElement("td");
  var touchTable = createTable(this.ySegments, this.xSegments, "touch",
                               "touchpad-test-sector-untested");
  touchTableCell.appendChild(touchTable);
  row.appendChild(touchTableCell);

  var scrollTableCell = document.createElement("td");
  var scrollTable = createTable(this.ySegments, 1, "scroll",
                                "touchpad-test-sector-untested");
  scrollTableCell.appendChild(scrollTable);
  row.appendChild(scrollTableCell);

  tableBody.appendChild(row);
  table.appendChild(tableBody);
  $(this.container).appendChild(table);
  this.updateCircleCountText();
};

/**
 * Marks the given (x,y) sector as "tested" on the test ui.
 * @param {int} x
 * @param {int} y
 */
TouchpadTest.prototype.markSectorTested = function(x, y) {
  var id = "touch-x-" + x + "-y-" + y;
  var element = document.getElementById(id);
  if (element) {
    element.className = "touchpad-test-sector-tested";
  }
  this.checkTestComplete();
};

/**
 * Marks the given y scroll sector as "tested" on the test ui.
 * @param {int} y
 */
TouchpadTest.prototype.markScrollSectorTested = function(y) {
  var id = "scroll-x-0-y-" + y;
  var element = document.getElementById(id);
  if (element) {
    element.className = "touchpad-test-sector-tested";
  }
  this.checkTestComplete();
};

/**
 * Marks the given circle as "tested" on the test ui.
 * @param {string} id
 */
TouchpadTest.prototype.markCircleTested = function(id) {
  var element = document.getElementById(id);
  if (element) {
    element.className = "touchpad-test-circle-tested";
  }
  this.checkTestComplete();
};

/**
 * Updates the text of the circle cells on the test ui.
 */
TouchpadTest.prototype.updateCircleCountText = function() {
  $("left-text-cell").innerHTML = this.leftCount.toString() + " / "
                                  + this.countTarget.toString();
  $("right-text-cell").innerHTML = this.rightCount.toString() + " / "
                                  + this.countTarget.toString();
};

/**
 * Adds one count to the left circle count.
 */
TouchpadTest.prototype.updateLeftCount = function() {
  if (this.leftCount < this.countTarget) {
    this.leftCount = this.leftCount + 1;
  }
};

/**
 * Adds one count to the right circle count.
 */
TouchpadTest.prototype.updateRightCount = function() {
  if (this.rightCount < this.countTarget) {
    this.rightCount = this.rightCount + 1;
  }
};

/**
 * Marks the given circle as "down" on the test ui.
 * @param {string} id
 */
TouchpadTest.prototype.markCircleDown = function(id) {
  var element = document.getElementById(id);
  if (element) {
    element.className = "touchpad-test-circle-down";
  }
};

/**
 * Checks if test is completed by checking the number of sectors that
 * haven't passed the test. Also check that click counts reach target or not.
 */
TouchpadTest.prototype.checkTestComplete = function() {
  if ((this.getClassArray("touchpad-test-sector-untested").length == 0) &&
      (this.leftCount == this.countTarget) &&
      (this.rightCount == this.countTarget)) {
    window.test.pass();
  }
};

/**
 * Fails the test and prints out all the failed items.
 */
TouchpadTest.prototype.failTest = function() {
  var failedSectors = new Array();

  this.getClassArray("touchpad-test-sector-untested").forEach(
    function(element) {
      failedSectors.push((element.id));
    }
  );

  this.failMsg = "Touchpad test failed. Malfunction sectors:";
  failedSectors.forEach(function(element, index, array) {
    this.failMsg += " " + element;
    if (index != array.length -1) {
      this.failMsg += ",";
    }
  }, this);
  if (this.leftCount < this.countTarget) {
    this.failMsg += " left click count: " + $("left-text-cell").innerHTML;
  }
  if (this.rightCount < this.countTarget) {
    this.failMsg += " right click count: " + $("right-text-cell").innerHTML;
  }
  window.test.fail(this.failMsg);
};

/**
 * Returns an Array coverted from the NodeList of the given class.
 * @param {string} className
 * @return Array
 */
TouchpadTest.prototype.getClassArray = function(className) {
  return Array.prototype.slice.call(document.getElementsByClassName(className));
};

/**
 * Creates a table element with specified row number and column number.
 * Each td in the table contains one div with id prefix-x-x_number-y-y_number
 * and the specified CSS class.
 * @param {int} rowNumber
 * @param {int} colNumber
 * @param {String} prefix
 * @param {String} className
 */
function createTable(rowNumber, colNumber, prefix, className) {
  var table = document.createElement("table");
  table.style.width = "100%";
  table.style.height = "100%";
  var tableBody = document.createElement("tbody");
  for (var y = 0; y < rowNumber; ++y) {
    var row = document.createElement("tr");
    for (var x = 0; x < colNumber; ++x) {
      var cell = document.createElement("td");
      var div = document.createElement("div");
      div.id = prefix + "-x-" + x + "-" + "y-" + y;
      div.innerHTML = div.id;
      div.className = className;
      cell.appendChild(div);
      row.appendChild(cell);
    }
    tableBody.appendChild(row);
  }
  table.appendChild(tableBody);
  return table;
}

/**
 * Marks a secotr as tested.
 * @param {int} x
 * @param {int} y
 */
function markSectorTested(x, y) {
  window.touchpadTest.markSectorTested(x, y);
}

/**
 * Marks a scroll secotr as tested.
 * @param {int} y
 */
function markScrollSectorTested(y) {
  window.touchpadTest.markScrollSectorTested(y);
}

/**
 * Marks single click as down.
 */
function markSingleClickDown() {
  window.touchpadTest.markCircleDown("left-circle");
}

/**
 * Marks single click as tested.
 */
function markSingleClickUp() {
  window.touchpadTest.updateLeftCount();
  window.touchpadTest.updateCircleCountText();
  window.touchpadTest.markCircleTested("left-circle");
}

/**
 * Marks double click as down.
 */
function markDoubleClickDown() {
  window.touchpadTest.markCircleDown("right-circle");
}

/**
 * Marks double click as tested.
 */
function markDoubleClickUp() {
  window.touchpadTest.updateRightCount();
  window.touchpadTest.updateCircleCountText();
  window.touchpadTest.markCircleTested("right-circle");
}

/**
 * Fails the test.
 */
function failTest() {
  window.touchpadTest.failTest();
}
