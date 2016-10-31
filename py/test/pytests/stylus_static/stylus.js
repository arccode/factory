// Copyright (c) 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * Get the parametric representation of the projection point on the diagnoal
 * line.
 * @param {Object} canvas
 * @param {number} x
 * @param {number} y
 */
function getT(canvas, x, y) {
  var dd = canvas.width ** 2 + canvas.height ** 2;
  return (canvas.width * x + canvas.height * (canvas.height - y)) / dd;
}

/**
 * Get the XY coordinate of a parametric representation plus a given offset.
 * @param {Object} canvas
 * @param {number} t
 * @param {number} offset
 */
function getXY(canvas, t, offset) {
  var d = Math.sqrt(canvas.width ** 2 + canvas.height ** 2);
  var x = canvas.width * t + canvas.height / d * offset;
  var y = canvas.height * (1 - t) + canvas.width / d * offset;
  return [x, y];
}

/**
 * Draw a red boundary line.
 * @param {Object} canvas
 * @param {Object} ctx
 * @param {number} offset
 */
function drawBoundaryLine(canvas, ctx, offset) {
  ctx.beginPath();
  var xy = getXY(canvas, 0, offset);
  ctx.moveTo(xy[0], xy[1]);
  xy = getXY(canvas, 1, offset);
  ctx.lineTo(xy[0], xy[1]);
  ctx.strokeStyle = "red";
  ctx.stroke();
}

/**
 * Draw a green progress line.
 * @param {Object} canvas
 * @param {Object} ctx
 * @param {number} t
 */
function drawProgressLine(canvas, ctx, t) {
  var xy = getXY(canvas, t, 0);
  ctx.beginPath();
  ctx.moveTo(0, canvas.height);
  ctx.lineTo(xy[0], xy[1]);
  ctx.strokeStyle = "green";
  ctx.stroke();
}

/**
 * StylusTest constructor.
 * @param {Object} canvas
 * @param {int} error_margin
 * @param {number} begin_position
 * @param {number} end_position
 * @param {number} step_size
 */
function StylusTest(canvas, error_margin,
                    begin_position, end_position, step_size) {
  this.canvas = canvas;
  canvas.style["background-color"] = "white";
  this.ctx = canvas.getContext("2d");
  this.error_margin = error_margin;
  drawBoundaryLine(canvas, this.ctx, -error_margin);
  drawBoundaryLine(canvas, this.ctx, +error_margin);
  this.last_position = begin_position;
  drawProgressLine(canvas, this.ctx, this.last_position);
  this.end_position = end_position;
  this.step_size = step_size;
}

/**
 * Unhide the canvas.
 */
StylusTest.prototype.showCanvas = function() {
  this.canvas.style["display"] = "";
};

/**
 * Handle an input event.
 * @param {number} x_ratio
 * @param {number} y_ratio
 */
StylusTest.prototype.handler = function(x_ratio, y_ratio) {
  var x = x_ratio * this.canvas.width;
  var y = y_ratio * this.canvas.height;
  var t = getT(this.canvas, x, y);
  var xyt = getXY(this.canvas, t, 0);
  var xt = xyt[0], yt = xyt[1];
  var d = Math.sqrt((x - xt) ** 2 + (y - yt) ** 2);
  if(d > this.error_margin) {
    window.test.fail(
        "Distance " + d + " larger than error margin " + this.error_margin);
  }
  if(t <= this.last_position || t > this.last_position + this.step_size) {
    return;
  }
  this.ctx.beginPath();
  this.ctx.moveTo(x, y);
  this.ctx.lineTo(xt, yt);
  this.ctx.strokeStyle = "blue";
  this.ctx.stroke();
  this.last_position = t;
  drawProgressLine(this.canvas, this.ctx, this.last_position);
  if(t >= this.end_position) window.test.pass();
};

/**
 * Fail the test.
 */
function failTest() {
  window.test.fail("Operator marked fail.");
}

/**
 * Set up a stylus test.
 * @param {string} canvasId
 * @param {int} error_margin
 * @param {number} begin_position
 * @param {number} end_position
 * @param {number} step_size
 */
function setupStylusTest(canvasId, error_margin,
                         begin_position, end_position, step_size) {
  var canvas = document.getElementById(canvasId);
  canvas.width = screen.width;
  canvas.height = screen.height;
  window.stylusTest = new StylusTest(canvas, error_margin,
                                     begin_position, end_position, step_size);
}

/**
 * Show the canvas in fullscreen.
 */
function startTest() {
  window.test.setFullScreen(true);
  window.stylusTest.showCanvas();
}

/**
 * Pass an input event.
 * @param {number} x_ratio
 * @param {number} y_ratio
 */
function handler(x_ratio, y_ratio) {
  window.stylusTest.handler(x_ratio, y_ratio);
}
