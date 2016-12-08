// Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * API for keyboard test.
 * @constructor
 * @param {string} layout
 * @param {Object} bindings
 * @param {Object} skipKeycodes
 * @param {string} container
 * @param {Array} keyOrderList
 * @param {boolean} strictSequentialPress
 * @param {boolean} allowMultiKeys
 */
var keyboardTest = function(layout, bindings, skipKeycodes, container,
    keyOrderList, strictSequentialPress, allowMultiKeys) {
  this.layout = layout;
  this.bindings = bindings;
  this.skipKeycodes = skipKeycodes;
  this.container = container;
  this.keyOrderList = keyOrderList;
  this.strictSequentialPress = strictSequentialPress;
  this.next_key_index = 0;
  if (allowMultiKeys) {
    this.enInstruct = '';
    this.zhInstruct = '';
  } else {
    this.enInstruct = 'Press one key at a time.';
    this.zhInstruct = '一次只能按一个键';
  }
};

/**
 * Initializes keyboard layout image and div elements.
 */
keyboardTest.prototype.init = function() {
  var img = new Image();
  var container = this.container;
  var bindings = this.bindings;
  var skipKeycodes = this.skipKeycodes;
  img.id = 'layout-image';
  img.onload = function() {
    var xOffset = ($(container).clientWidth - this.width) / 2;
    for (var keycode in bindings) {
      var skip = keycode in skipKeycodes;
      for (var i = 0; i < bindings[keycode].length; ++i) {
        var div = document.createElement('div');
        div.id = 'keycode-' + keycode + '-' + i;
        div.style.position = 'absolute';
        div.style.left = xOffset + bindings[keycode][i][0];
        div.style.top = bindings[keycode][i][1];
        div.style.width = bindings[keycode][i][2];
        div.style.height = bindings[keycode][i][3];
        div.style.zIndex = 2;
        div.className =
            skip ? 'keyboard-test-key-skip' : 'keyboard-test-key-untested';
        $(container).appendChild(div);
      }
    }
  };
  img.src = this.layout + '.png';
  $(container).appendChild(img);
  var instruction = document.createElement('div');
  appendSpanEnZh(instruction, this.enInstruct, this.zhInstruct);
  $(container).appendChild(instruction);
};

/**
 * Marks the given keycode as "keydown" on the test ui. There may be multiple
 * div tags mapping to the same keycode, so we have to iterate through all the
 * div elements.
 * @param {number} keycode
 */
keyboardTest.prototype.markKeydown = function(keycode) {
  var divs = this.getClassArray('keyboard-test-key-untested');
  if (!divs.length) {
    return;
  }

  if (this.keyOrderList && this.keyOrderList.indexOf(keycode) != -1) {
    // Checks if the key has been pressed following the given order.
    var index = this.keyOrderList.indexOf(keycode);
    if (this.strictSequentialPress) {
      // Check the keys in the strict sequential manner.
      if (index != this.next_key_index) {
        var failMsg =
            'expect keycode ' + this.keyOrderList[this.next_key_index] +
            ' but get keycode ' + keycode;
        this.failTest(failMsg);
      } else {
        this.next_key_index += 1;
      }
    } else {
      // Check the keys in a somewhat relaxed sequential manner.
      if (index > 0) {
        var untested = this.getClassArray('keyboard-test-key-untested');
        for (var i = 0; i < untested.length; ++i) {
          if (this.matchKeycode(untested[i].id, this.keyOrderList[index - 1])) {
            // Returns if the previous key is untested.
            return;
          }
        }
      }
    }
  }
  divs.forEach(function(element) {
      if (!element) return;
      if (this.matchKeycode(element.id, keycode)) {
        element.className = 'keyboard-test-keydown';
      }
    }, this);
};

/**
 * Marks the given keycode as "keyup" on the test ui. There may be multiple
 * div tags mapping to the same keycode, so we have to iterate through all the
 * div elements.
 * @param {number} keycode
 */
keyboardTest.prototype.markKeyup = function(keycode) {
  var divs = this.getClassArray('keyboard-test-keydown');
  if (!divs.length) {
    return;
  }
  divs.forEach(function(element) {
      if (!element) return;
      if (this.matchKeycode(element.id, keycode)) {
        element.className = 'keyboard-test-keyup';
      }
    }, this);
  this.checkTestComplete();
};

/**
 * Resets the test by settings all keys to untested
 */
keyboardTest.prototype.resetTest = function() {
  function reset(element) {
    element.className = 'keyboard-test-key-untested';
  }
  this.getClassArray('keyboard-test-keydown').forEach(reset);
  this.getClassArray('keyboard-test-keyup').forEach(reset);
};

/**
 * Checks if test is completed by checking the number of keys haven't passed
 * the test.
 */
keyboardTest.prototype.checkTestComplete = function() {
  if (this.getClassArray('keyboard-test-key-untested').length == 0 &&
      this.getClassArray('keyboard-test-key-keydown').length == 0) {
    window.test.pass();
  }
};

/**
 * Fails the test and prints out all the failed keys.
 * @param {string} failMsg
 */
keyboardTest.prototype.failTest = function(failMsg) {
  window.test.fail(failMsg);
};

/**
 * Fails the test and prints out all the failed keys.
 */
keyboardTest.prototype.failTestTimeout = function() {
  var failedKeys = new Array();

  function getKeyCode(divId) {
    var codeLength = divId.lastIndexOf('-') - divId.indexOf('-') - 1;
    return parseInt(divId.substr(divId.indexOf('-') + 1, codeLength), 10);
  }

  this.getClassArray('keyboard-test-key-untested').forEach(function(element) {
    failedKeys.push(getKeyCode(element.id));
  });
  this.getClassArray('keyboard-test-keydown').forEach(function(element) {
    failedKeys.push(getKeyCode(element.id));
  });

  this.failMsg = 'Keyboard test failed. Malfunction keys:';
  failedKeys.forEach(function(element, index, array) {
    this.failMsg += ' ' + element;
    if (index != array.length - 1) {
      this.failMsg += ',';
    }
  }, this);
  this.failTest(this.failMsg);
};

/**
 * Checks if the given id matches the given keycode.
 * @param {string} id
 * @param {number} keycode
 * @return {boolean}
 */
keyboardTest.prototype.matchKeycode = function(id, keycode) {
  return id.indexOf('keycode-' + keycode + '-') == 0;
};

/**
 * Returns an Array coverted from the NodeList of the given class.
 * @param {string} className
 * @return {Array}
 */
keyboardTest.prototype.getClassArray = function(className) {
  return Array.prototype.slice.call(document.getElementsByClassName(className));
};

/**
 * Creates a keyboard test and runs it.
 * @param {string} layout
 * @param {Object} bindings
 * @param {Object}  skipKeycodes
 * @param {string} container
 * @param {Array} keyOrderList
 * @param {boolean} strictSequentialPress
 * @param {boolean} allowMultiKeys
 */
function setUpKeyboardTest(layout, bindings, skipKeycodes, container,
    keyOrderList, strictSequentialPress, allowMultiKeys) {
  window.keyboardTest = new keyboardTest(layout, bindings, skipKeycodes,
      container, keyOrderList, strictSequentialPress, allowMultiKeys);
  window.keyboardTest.init();
}

/**
 * Marks a key as keydown.
 * @param {number} keycode
 */
function markKeydown(keycode) {
  window.keyboardTest.markKeydown(keycode);
}

/**
 * Marks a key as keyup.
 * @param {number} keycode
 */
function markKeyup(keycode) {
  window.keyboardTest.markKeyup(keycode);
}

/**
 * Fails the test.
 * @param {string} failMsg
 */
function failTest(failMsg) {
  window.keyboardTest.failTest(failMsg);
}

/**
 * Fails the test due to timeout.
 */
function failTestTimeout() {
  window.keyboardTest.failTestTimeout();
}

/**
 * Appends en span and zh span to the input element.
 * @param {Element} div the element we to which we want to append spans.
 * @param {string} en the English text to append.
 * @param {string} zh the Simplified-Chinese text to append.
 */
function appendSpanEnZh(div, en, zh) {
  var en_span = document.createElement('span');
  var zh_span = document.createElement('span');
  en_span.className = 'goofy-label-en';
  en_span.innerHTML = en;
  zh_span.className = 'goofy-label-zh';
  zh_span.innerHTML = zh;
  div.appendChild(en_span);
  div.appendChild(zh_span);
}
