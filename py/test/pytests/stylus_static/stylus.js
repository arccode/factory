// Copyright 2017 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

class Vector {
  /**
   * Two-dimensional vector.
   * @param {number} x
   * @param {number} y
   */
  constructor(x, y) {
    this.x = x;
    this.y = y;
  }
}

/**
 * Vector addition.
 * @param {Vector} a
 * @param {Vector} b
 * @return {Vector}
 */
const add = (a, b) => new Vector(a.x + b.x, a.y + b.y);

/**
 * Element-wise vector multiplication.
 * @param {Vector} a
 * @param {Vector} b
 * @return {Vector}
 */
const mul_ew = (a, b) => new Vector(a.x * b.x, a.y * b.y);

/**
 * Vector scalar multiplication.
 * @param {Vector} v
 * @param {number} k
 * @return {Vector}
 */
const mul_scalar = (v, k) => new Vector(v.x * k, v.y * k);

/**
 * Vector subtraction.
 * @param {Vector} a
 * @param {Vector} b
 * @return {Vector}
 */
const sub = (a, b) => add(a, mul_scalar(b, -1));

/**
 * Vector dot product.
 * @param {Vector} a
 * @param {Vector} b
 * @return {number}
 */
const dot = (a, b) => a.x * b.x + a.y * b.y;

/**
 * Vector absolute square.
 * @param {Vector} v
 * @return {number}
 */
const abs2 = (v) => dot(v, v);

class Line {
  /**
   * Line segment.
   * @param {Vector} begin
   * @param {Vector} end
   */
  constructor(begin, end) {
    this.begin = begin;
    this.v = sub(end, begin);
    const nv = new Vector(-this.v.y, this.v.x);
    // Unit normal vector of `this.v`.
    this.unv = mul_scalar(nv, 1 / Math.sqrt(abs2(nv)));
  }

  /**
   * Get the parametric representation of the projection point on the line.
   * @param {Vector} p
   * @return {number}
   */
  getT(p) {
    return dot(this.v, sub(p, this.begin)) / abs2(this.v);
  }

  /**
   * Get the XY coordinate of a parametric representation.
   * @param {number} t
   * @return {Vector}
   */
  getXY(t) {
    return add(this.begin, mul_scalar(this.v, t));
  }
}

class StylusTest {
  /**
   * StylusTest constructor.
   * @param {number} error_margin
   * @param {number} begin_ratio
   * @param {number} end_ratio
   * @param {number} step_ratio
   * @param {Array<Vector>} endpoints_ratio
   */
  constructor(
      error_margin, begin_ratio, end_ratio, step_ratio, endpoints_ratio) {
    this.canvas = document.getElementById('canvas');
    this.canvas.className = 'fullscreen';
    this.canvas.width = screen.width;
    this.canvas.height = screen.height;
    this.ctx = this.canvas.getContext('2d');
    this.error_margin = error_margin;
    this.end_ratio = end_ratio;
    this.step_ratio = step_ratio;
    this.size = new Vector(this.canvas.width, this.canvas.height);
    this.line = new Line(
        mul_ew(endpoints_ratio[0], this.size),
        mul_ew(endpoints_ratio[1], this.size));

    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.drawBoundaryLines();
    this.last_ratio = begin_ratio;
    this.drawProgressLine();
  }

  /**
   * Process an input event.
   * @param {Vector} p_ratio
   */
  handler(p_ratio) {
    const p = mul_ew(p_ratio, this.size);
    const t = this.line.getT(p);
    const q = this.line.getXY(t);
    const d = Math.sqrt(abs2(sub(q, p)));
    if (d > this.error_margin) {
      window.test.fail(
          `Distance ${d} larger than error margin ${this.error_margin}`);
    }
    if (t <= this.last_ratio || t > this.last_ratio + this.step_ratio) {
      return;
    }
    this.drawLine(p, q, 'blue');
    this.last_ratio = t;
    this.drawProgressLine();
    if (t >= this.end_ratio) window.test.pass();
  }

  /**
   * Draw a color line connecting `p` and `q`.
   * @param {Vector} p
   * @param {Vector} q
   * @param {string} color
   */
  drawLine(p, q, color) {
    this.ctx.beginPath();
    this.ctx.moveTo(p.x, p.y);
    this.ctx.lineTo(q.x, q.y);
    this.ctx.strokeStyle = color;
    this.ctx.stroke();
  }

  /**
   * Draw two red boundary lines.
   */
  drawBoundaryLines() {
    for(const side of [-1, +1]) {
      const d = mul_scalar(this.line.unv, side * this.error_margin);
      this.drawLine(
          add(this.line.getXY(-1), d), add(this.line.getXY(2), d), 'red');
    }
  }

  /**
   * Draw a green progress line.
   */
  drawProgressLine() {
    this.drawLine(this.line.begin, this.line.getXY(this.last_ratio), 'green');
  }
}

/**
 * Set up a stylus test.
 * @param {number} error_margin
 * @param {number} begin_ratio
 * @param {number} end_ratio
 * @param {number} step_ratio
 * @param {Array<Array<number>>} endpoints_ratio
 */
const setupStylusTest =
    (error_margin, begin_ratio, end_ratio, step_ratio, endpoints_ratio) => {
      window.test.setFullScreen(true);
      window.stylusTest = new StylusTest(
          error_margin, begin_ratio, end_ratio, step_ratio,
          endpoints_ratio.map(
              ([x_ratio, y_ratio]) => new Vector(x_ratio, y_ratio)));
    };

/**
 * Hide stylus test canvas.
 */
const hideStylusTest = () => {
  document.getElementById('canvas').classList.add('hidden');
  window.test.setFullScreen(false);
};

/**
 * Pass input events.
 * @param {Array<Array<number>>} xy_ratios
 */
const handler = xy_ratios => {
  xy_ratios.forEach(
      xy_ratio => window.stylusTest.handler(
          new Vector(xy_ratio[0], xy_ratio[1])));
};

const exports = {
  setupStylusTest,
  hideStylusTest,
  handler
};
for (const key of Object.keys(exports)) {
  window[key] = exports[key];
}
