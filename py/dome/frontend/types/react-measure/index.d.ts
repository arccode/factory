// Copyright 2018 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// @types/react-measure only have type for react-measure v2. This is a simple
// type definition to meet our need for v1.

declare module 'react-measure' {

  import getNodeDimensions from 'get-node-dimensions';
  import React from 'react';

  interface MeasureProps {
    onMeasure: (dimension: ReturnType<typeof getNodeDimensions>) => void;
  }

  export default class Measure extends React.Component<MeasureProps> {
  }
}
