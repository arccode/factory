/* Copyright 2018 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {Component, OnInit} from '@angular/core';
import {TestListService} from '../test-list.service';

/**
 * Componnet showing test list.
 */
@Component({
  selector: 'app-test-list',
  templateUrl: './test-list.component.html',
  styleUrls: ['./test-list.component.css']
})
export class TestListComponent implements OnInit {
  /** List of tests. */
  tests: string[] = [];

  constructor(private readonly testListService: TestListService) {}

  ngOnInit(): void {
    this.loadTestList();
  }

  /** Load test list. */
  private loadTestList(): void {
    this.tests = Object.keys(this.testListService.getTestList());
  }

  /** Tell `testListService` that a new test is selected. */
  onSelect(test: string): void {
    console.log(`selected test: ${test}`);

    this.testListService.setCurrentTest(test);
  }
}
