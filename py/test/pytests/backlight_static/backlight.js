// Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.


/**
 * API for backlight test.
 * @constructor
 * @param {string} container
 */
BacklightTest = function(container) {
  this.container = container;
  this.enInstruct = "Press Space to change backlight;<br>"
                  + "Press Esc to resume backlight;<br>"
                  + "After checking, Enter H for high intensity backlight;<br>"
                  + "L for low intensity backlight"
  this.zhInstruct = "按空格键调整亮度;<br>"
                  + "按Esc复原亮度;<br>"
                  + "检查后若为提高亮度输入H; 若为降低亮度输入L";
};


/**
 * Initializes backlight test ui.
 * There is a caption for instructions.
 */
BacklightTest.prototype.init = function() {
  appendSpanEnZh($(this.container), this.enInstruct, this.zhInstruct);
  $(this.container).className = "backlight-caption";
};


/**
 * Creates a backlight test and runs it.
 * @param {string} container
 */
function setupBacklightTest(container) {
  window.backlightTest = new BacklightTest(container);
  window.backlightTest.init();
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
