// Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for display test.
 * @constructor
 * @param {string} container
 * @param {Array.<string>} colors
 */
DisplayTest = function(container, colors) {
  this.container = container;
  this.display = false;
  this.focusItem = 0;
  this.styleDiv = null;
  this.fullScreenElement = null;
  this.allStyleList = [
    "display-subtest-solid-gray-170",
    "display-subtest-solid-gray-127",
    "display-subtest-solid-gray-63",
    "display-subtest-solid-red",
    "display-subtest-solid-green",
    "display-subtest-solid-blue",
    "display-subtest-solid-white",
    "display-subtest-solid-gray",
    "display-subtest-solid-black",
    "display-subtest-grid",
    "display-subtest-rectangle",
    "display-subtest-gradient-red",
    "display-subtest-gradient-green",
    "display-subtest-gradient-blue",
    "display-subtest-gradient-white",
    "display-subtest-image-complex",
    "display-subtest-image-black",
    "display-subtest-image-white",
    "display-subtest-image-crosstalk-black",
    "display-subtest-image-crosstalk-white",
    "display-subtest-image-gray-63",
    "display-subtest-image-gray-127",
    "display-subtest-image-gray-170",
    "display-subtest-image-horizontal-rgbw",
    "display-subtest-image-vertical-rgbw",
  ];
  this.allEnItemList = [
    "solid-gray-170",
    "solid-gray-127",
    "solid-gray-63",
    "solid-red",
    "solid-green",
    "solid-blue",
    "solid-white",
    "solid-gray",
    "solid-black",
    "grid",
    "rectangle",
    "gradient-red",
    "gradient-green",
    "gradient-blue",
    "gradient-white",
    "image-complex.bmp",
    "image-BLACK.BMP",
    "image-WHITE.BMP",
    "image-CrossTalk(black).bmp",
    "image-CrossTalk(white).bmp",
    "image-gray(63).bmp",
    "image-gray(127).bmp",
    "image-gray(170).bmp",
    "image-Horizontal(RGBW).bmp",
    "image-Vertical(RGBW).bmp",
  ];
  this.allZhItemList = [
    "灰色170",
    "灰色127",
    "灰色63",
    "红色",
    "绿色",
    "蓝色",
    "白色",
    "灰色",
    "黑色",
    "格框",
    "矩形",
    "渐红",
    "渐绿",
    "渐蓝",
    "渐白",
    "影像-复杂",
    "影像-黑色",
    "影像-白色",
    "影像-方形-黑色",
    "影像-方形-白色",
    "影像-灰色63",
    "影像-灰色127",
    "影像-灰色170",
    "影像-水平",
    "影像-垂直",
  ];
  this.enPassed = "Passed";
  this.zhPassed = "通过";
  this.enFailed = "Failed";
  this.zhFailed = "失败";
  this.enUntested = "Untested";
  this.zhUntested = "未经测试";
  this.enInstruct = "Press Space to display;<br>"
                  + "After checking, Enter to pass; Esc to fail.";
  this.zhInstruct = "按空格键显示;<br>"
                  + "检查后按Enter键通过; 按Esc键失败。";
  this.gridWidth = 10;
  this.gridHeight = 10;
  this.gridStyleCSS = ""
    + ".display-subtest-grid"
    + "{background-color: white; width: 100%; height: 100%; }"
    + ".display-subtest-grid-div"
    + "{background-color: black; width: " + this.gridWidth + ";"
    + " height: " + this.gridHeight +";"
    + " border: 5px solid; }";
  this.enItemList = [];
  this.zhItemList = [];
  this.styleList = [];
  //Puts the selected colors into enItemList, zhItemList, and styleList.
  for (var item = 0; item < colors.length; ++item) {
    index = this.allEnItemList.indexOf(colors[item])
    if (index >= 0) {
      this.enItemList.push(this.allEnItemList[index]);
      this.zhItemList.push(this.allZhItemList[index]);
      this.styleList.push(this.allStyleList[index]);
    }
  }
  this.itemNumber = this.enItemList.length;
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
  var caption = document.createElement("div");
  caption.className = "display-caption";
  appendSpanEnZh(caption, this.enInstruct, this.zhInstruct);
  $(this.container).appendChild(caption);

  var table = document.createElement("table");
  table.className = "display-table";
  var tableBody = document.createElement("tbody");
  for (var item = 0; item < this.itemNumber; ++item) {
    var row = document.createElement("tr");

    var itemName = document.createElement("td");
    itemName.className = "display-subtest-td";
    itemName.style.width = "50%";
    appendSpanEnZh(itemName, this.enItemList[item], this.zhItemList[item]);
    row.appendChild(itemName);

    var itemStatus = document.createElement("td");
    itemStatus.id = "item-" + item + "-status";
    itemStatus.itemName = this.enItemList[item];
    itemStatus.className = "display-subtest-untested";
    appendSpanEnZh(itemStatus, this.enUntested, this.zhUntested);

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
  this.fullScreenElement = document.createElement("div");
  this.fullScreenElement.className = "display-full-screen-hide";
  $(this.container).appendChild(this.fullScreenElement);
};

/**
 * Initializes display style for fullscreen grid display.
 * Other display styles are set in display.css
 */
DisplayTest.prototype.setupGridStyle = function() {
  this.styleElement = document.createElement("style");
  this.styleElement.innerHTML = this.gridStyleCSS;
  this.fullScreenElement.appendChild(this.styleElement);

};

/**
 * Initializes display div in fullscreen element.
 */
DisplayTest.prototype.setupDisplayDiv = function() {
  this.displayDiv = document.createElement("div");
  this.displayDiv.id = "display-div";
  this.fullScreenElement.appendChild(this.displayDiv);
};

/**
 * Setups display div style. Grids need to be taking care of separately.
 */
DisplayTest.prototype.setDisplayDivClass = function() {
  var displayBeforeSetting = this.display;
  //cleans up display div
  this.displayDiv.innerHTML = "";
  this.displayDiv.className = this.styleList[this.focusItem];
  if (this.displayDiv.className == "display-subtest-grid") {
    //Switches display on here so we can create grid
    //using correct width/height of display div when it is
    //in fullscreen. Uses displayBeforeSetting to restore display.
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
  var gridTable = document.createElement("table");
  gridTable.style.width = "100%";
  gridTable.style.height = "100%";
  var gridTableBody = document.createElement("tbody");
  for (var y = 0; y < ySegments; ++y) {
    var row = document.createElement("tr");
    for (var x = 0; x < xSegments; ++x) {
      var cell = document.createElement("td");
      var div = document.createElement("div");
      div.id = "x-" + x + "-" + "y-" + y;
      div.className = "display-subtest-grid-div";
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
  //If current display is on, turns it off
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
  this.fullScreenElement.className = "display-full-screen-show";
  window.test.setFullScreen(true);
};

/**
 * Switches the fullscreen display off. Sets fullScreenElement
 * visibility to hidden and restores the test iframe to normal.
 */
DisplayTest.prototype.switchDisplayOff = function() {
  this.display = false;
  this.fullScreenElement.className = "display-full-screen-hide";
  window.test.setFullScreen(false);
};


/**
 * Changes the status in test table based success or not.
 * Setups the display style for the next subtest.
 * Judges the whole test if there is no more subtests.
 * @param {boolean} success.
 */
DisplayTest.prototype.judgeSubTest = function(success) {
  var id = "item-" + this.focusItem + "-status";
  var element = document.getElementById(id);
  if (element) {
    element.innerHTML="";
    if (success) {
      element.className = "display-subtest-passed";
      appendSpanEnZh(element, this.enPassed, this.zhPassed);
    } else {
      element.className = "display-subtest-failed";
      appendSpanEnZh(element, this.enFailed, this.zhFailed);
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
  if (this.getClassArray("display-subtest-passed").length == this.itemNumber) {
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

  this.getClassArray("display-subtest-failed").forEach(
    function(element) {
      failedItems.push((element.itemName));
    }
  );

  this.failMsg = "Display test failed. Malfunction items:";
  failedItems.forEach(function(element, index, array) {
    this.failMsg += " " + element;
    if (index != array.length -1) {
      this.failMsg += ",";
    }
  }, this);
  window.test.fail(this.failMsg);
};

/**
 * Returns an Array coverted from the NodeList of the given class.
 * @param {string} className
 * @return Array
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

/**
 * Appends en span and zh span to the input element.
 * @param {Element} div the element we to which we want to append spans.
 * @param {string} en the English text to append.
 * @param {string} zh the Simplified-Chinese text to append.
 * @return Array
 */
function appendSpanEnZh(div, en, zh) {
  var en_span = document.createElement("span");
  var zh_span = document.createElement("span");
  en_span.className = "goofy-label-en";
  en_span.innerHTML = en;
  zh_span.className = "goofy-label-zh";
  zh_span.innerHTML = zh;
  div.appendChild(en_span);
  div.appendChild(zh_span);
}
