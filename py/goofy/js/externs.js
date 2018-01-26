// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// This file provides type informations for libraries that are not compiled with
// closure compiler.

/**
 * @constructor
 * @param {!Object} setting
 */
const Terminal = function(setting) {};

/** @type {function(string, function(string))} */
Terminal.prototype.on;

/** @type {function(!Element)} */
Terminal.prototype.open;

/** @type {function(string)} */
Terminal.prototype.write;

/** @type {function(number, number)} */
Terminal.prototype.resize;

/** @type {function(number, number)} */
Terminal.prototype.refresh;

/** @type {number} */
Terminal.prototype.cols;

/** @type {number} */
Terminal.prototype.rows;

/** @type {!Element} */
Terminal.prototype.element;

const Base64 = {};

/** @type {function(string): string} */
Base64.encode = function(s) {};

/** @type {function(string): string} */
Base64.decode = function(s) {};

/** @type {function(!Node): !jQuery.Type} */
const jQuery = function(e) {};

/** @constructor */
jQuery.Type = function() {};

/** @type {function(string): !jQuery.Type} */
jQuery.Type.prototype.find;

/** @type {function(!Object)} */
jQuery.Type.prototype.draggable;

/** @type {function(string, string=): string} */
jQuery.Type.prototype.css;

/** @type {function(): number} */
jQuery.Type.prototype.width;

/** @type {function(): number} */
jQuery.Type.prototype.height;

/** @type {function(!Object=)} */
jQuery.Type.prototype.resizable;

/** @type {function(string, function())} */
jQuery.Type.prototype.bind;

// Some missing method types from closure library.

/** @type {function(!Node)} */
Node.prototype.prepend;
