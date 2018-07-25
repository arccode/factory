/* Copyright 2018 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {
  Component,
  ComponentFactoryResolver,
  OnInit,
  Type,
  ViewChild,
} from '@angular/core';

import {TestCase} from './interfaces/test-case';
import {TestListService} from './test-list.service';
import {TestDirective} from './test.directive';

/**
 * Main component of the application.
 */
@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css'],
})
export class AppComponent implements OnInit {
  /** Title of the application. */
  title: string = 'ChromeOS Diagnosis Tool';

  /** Mapping of test name to test case. */
  tests: {[testName: string]: Type<TestCase>} = {};

  /** Directive to load a test case. */
  @ViewChild(TestDirective) testLoader!: TestDirective;

  constructor(
      private readonly testListService: TestListService,
      private readonly componentFactoryResolver: ComponentFactoryResolver) { }

  ngOnInit(): void {
    this.loadTestList();

    this.testListService.testSelected.subscribe((test: string) => {
      this.handleTestSelected(test);
    });
  }

  /** Get test list from `testListService`. */
  loadTestList(): void {
    this.tests = this.testListService.getTestList();
  }

  /** Handle the `testSelected` event. */
  private handleTestSelected(test: string): void {
    console.log(`loading test: ${test}`);

    const factory =
        this.componentFactoryResolver.resolveComponentFactory(this.tests[test]);

    const viewContainerRef = this.testLoader.viewContainerRef;
    viewContainerRef.clear();

    const componentRef = viewContainerRef.createComponent(factory);
    const testCase = componentRef.instance;

    try {
      try {
        testCase.setUp();
        testCase.runTest();
      } finally {
        testCase.tearDown();
      }
    } catch (error) {
      console.log(`${testCase.getTestName()} Failed`);
      console.log(`error: ${error}`);
    }
  }
}
