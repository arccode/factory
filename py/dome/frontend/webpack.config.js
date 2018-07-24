// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

const convert = require('koa-convert');
const path = require('path');
const process = require('process');
const webpack = require('webpack');
const forkTsCheckerWebpackPlugin = require('fork-ts-checker-webpack-plugin');
const webpackHotMiddleware = require('koa-webpack-hot-middleware');
const tsconfigPathsWebpackPlugin = require('tsconfig-paths-webpack-plugin');

const config = {
  devtool: 'source-map',
  entry: ['./src/index'],
  mode: 'production',
  module: {
    rules: [{
      test: /\.tsx?$/,
      use: [{
        loader: 'ts-loader',
        options: {
          transpileOnly: true,
          experimentalWatchApi: true,
        },
      }],
    }],
  },
  name: 'main',
  output: {
    filename: 'app.js',
    path: path.resolve(__dirname, 'build'),
    pathinfo: false,
    publicPath: '/static/',
  },
  optimization: {
    noEmitOnErrors: true,
  },
  performance: {hints: false},
  plugins: [new forkTsCheckerWebpackPlugin(
      {workers: forkTsCheckerWebpackPlugin.TWO_CPUS_FREE, async: false})],
  resolve: {
    extensions: ['.ts', '.tsx', '.js'],
    plugins: [new tsconfigPathsWebpackPlugin()],
  },
};

if (process.env.WEBPACK_SERVE) {
  const wsPath = '/__hot_ws';

  config.entry.push(`webpack-hot-middleware/client?path=${wsPath}&reload=true`);
  config.plugins.push(new webpack.HotModuleReplacementPlugin());
  config.module.rules[0].use.unshift({loader: 'babel-loader'});
  config.devtool = 'eval-source-map';
  config.mode = 'development';

  config.serve = {
    add: (app, middleware, options) => {
      middleware.webpack();
      middleware.content();
      app.use(convert(webpackHotMiddleware(options.compiler, {
        path: wsPath,
      })));
    },
    clipboard: false,
    content: path.resolve(__dirname, 'src', 'static'),
    host: '0.0.0.0',
    // The webpack-hot-client that come with webpack-serve doesn't support
    // mounting the WebSocket server on a subpath, and has issues that cause it
    // hard to write reliable error overlay
    // (https://github.com/webpack-contrib/webpack-hot-client/issues/93), so we
    // use webpack-hot-middleware instead (which also has a native error
    // overlay!).
    hotClient: false,
    logTime: true,
  };
}

module.exports = config;
