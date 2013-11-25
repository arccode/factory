// Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for keyboard test.
 * @constructor
 * @param {string} layout
 * @param {Object} bindings
 * @param {string} container
 * @param {Array} keyOrderList
 */
keyboardTest = function(layout, bindings, container, keyOrderList) {
  this.layout = layout;
  this.bindings = bindings;
  this.container = container;
  this.keyOrderList = keyOrderList;
  this.enInstruct = "Press one key at a time.";
  this.zhInstruct = "一次只能按一个键";
};

/**
 * Initializes keyboard layout image and div elements.
 */
keyboardTest.prototype.init = function() {
  var img = new Image();
  var container = this.container;
  var bindings = this.bindings;
  img.id = "layout-image";
  img.onload = function () {
    var xOffset = ($(container).clientWidth - this.width) / 2;
    for (keycode in bindings) {
      for (var i = 0; i < bindings[keycode].length; ++i) {
        var div = document.createElement("div");
        div.id = "keycode-" + keycode + "-" + i;
        div.style.position = "absolute";
        div.style.left = xOffset + bindings[keycode][i][0];
        div.style.top = bindings[keycode][i][1];
        div.style.width = bindings[keycode][i][2];
        div.style.height = bindings[keycode][i][3];
        div.style.zIndex = 2;
        div.className = "keyboard-test-key-untested";
        $(container).appendChild(div)
      }
    }
  }
  img.src = this.layout + ".png";
  $(container).appendChild(img);
  var instruction = document.createElement("div");
  appendSpanEnZh(instruction, this.enInstruct, this.zhInstruct);
  $(container).appendChild(instruction);
};

/**
 * Marks the given keycode as "keydown" on the test ui. There may be multiple
 * div tags mapping to the same keycode, so we have to iterate through all the
 * div elements.
 * @param {int} keycode
 */
keyboardTest.prototype.markKeydown = function(keycode) {
  var divs = this.getClassArray("keyboard-test-key-untested");
  if (!divs.length) {
    return;
  }
  if (this.keyOrderList && this.keyOrderList.indexOf(keycode) != -1) {
    // Checks if the key has been pressed following the given order.
    var index = this.keyOrderList.indexOf(keycode);
    if (index > 0) {
      var untested = this.getClassArray("keyboard-test-key-untested");
      for (var i = 0; i < untested.length; ++i) {
        if (this.matchKeycode(untested[i].id, this.keyOrderList[index - 1])) {
          // Returns if the previous key is untested.
          return;
        }
      }
    }
  }
  divs.forEach(function(element) {
      if (!element)
        return;
      if (this.matchKeycode(element.id, keycode)) {
        element.className = "keyboard-test-keydown";
      }
    }, this);
};

/**
 * Marks the given keycode as "keyup" on the test ui. There may be multiple
 * div tags mapping to the same keycode, so we have to iterate through all the
 * div elements.
 * @param {int} keycode
 */
keyboardTest.prototype.markKeyup = function(keycode) {
  var divs = this.getClassArray("keyboard-test-keydown");
  if (!divs.length) {
    return;
  }
  divs.forEach(function(element) {
      if (!element)
        return;
      if (this.matchKeycode(element.id, keycode)) {
        element.className = "keyboard-test-keyup";
      }
    }, this);
  this.checkTestComplete();
};

/**
 * Resets the test by settings all keys to untested
 */
keyboardTest.prototype.resetTest = function() {
  function reset(element) {
    element.className = "keyboard-test-key-untested";
  }
  this.getClassArray("keyboard-test-keydown").forEach(reset);
  this.getClassArray("keyboard-test-keyup").forEach(reset);
};

/**
 * Checks if test is completed by checking the number of keys haven't passed
 * the test.
 */
keyboardTest.prototype.checkTestComplete = function() {
  if (this.getClassArray("keyboard-test-key-untested").length == 0 &&
      this.getClassArray("keyboard-test-key-keydown").length == 0) {
    window.test.pass();
  }
};

/**
 * Fails the test and prints out all the failed keys.
 */
keyboardTest.prototype.failTest = function() {
  var failedKeys = new Array();

  function getKeyCode(divId) {
    codeLength = divId.lastIndexOf("-") - divId.indexOf("-") - 1;
    return parseInt(divId.substr(divId.indexOf("-") + 1, codeLength));
  }

  this.getClassArray("keyboard-test-key-untested").forEach(function(element) {
    failedKeys.push(getKeyCode(element.id));
  });
  this.getClassArray("keyboard-test-keydown").forEach(function(element) {
    failedKeys.push(getKeyCode(element.id));
  });

  this.failMsg = "Keyboard test failed. Malfunction keys:";
  failedKeys.forEach(function(element, index, array) {
      this.failMsg += " " + element;
      if (index != array.length -1) {
        this.failMsg += ",";
      }
    }, this);
  window.test.fail(this.failMsg);
};

/**
 * Checks if the given id matches the given keycode.
 * @param {string} id
 * @param {int} keycode
 * @return boolean
 */
keyboardTest.prototype.matchKeycode = function(id, keycode) {
  return id.indexOf("keycode-" + keycode + "-") == 0;
};

/**
 * Returns an Array coverted from the NodeList of the given class.
 * @param {string} className
 * @return Array
 */
keyboardTest.prototype.getClassArray = function(className) {
  return Array.prototype.slice.call(document.getElementsByClassName(className));
};

/**
 * Creates a keyboard test and runs it.
 * @param {string} layout
 * @param {Object} bindings
 * @param {string} container
 * @param {Array} keyOrderList
 */
function setUpKeyboardTest(layout, bindings, container, keyOrderList) {
  window.keyboardTest = new keyboardTest(layout, bindings, container,
                                         keyOrderList);
  window.keyboardTest.init();
}

/**
 * Marks a key as keydown.
 * @param {int} keycode
 */
function markKeydown(keycode) {
  window.keyboardTest.markKeydown(keycode);
}

/**
 * Marks a key as keyup.
 * @param {int} keycode
 */
function markKeyup(keycode) {
  window.keyboardTest.markKeyup(keycode);
}

/**
 * Fails the test.
 */
function failTest() {
  window.keyboardTest.failTest();
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
