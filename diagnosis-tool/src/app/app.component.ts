/* Copyright 2018 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {
  Component,
  ComponentFactoryResolver,
  OnInit,
  ViewChild,
} from '@angular/core';

import {ArgSpec} from './interfaces/test-resource';
import {TestResource} from './interfaces/test-resource';
import {TestListService} from './test-list.service';
import {TestRunService, TestResult} from './test-run-service';
import {TestDirective} from './test.directive';

type TestState = 'IDLE'|'SETUP'|'ACTIVE';

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
  tests: {[testName: string]: TestResource} = {};

  logs: string[] = [];

  currentArgsSpec: ArgSpec[] = [];

  testState: TestState = 'IDLE';

  /** Directive to load a test case. */
  @ViewChild(TestDirective) testLoader!: TestDirective;

  constructor(
      private readonly testListService: TestListService,
      private readonly testRunService: TestRunService,
      private readonly componentFactoryResolver: ComponentFactoryResolver) {
    this.startTest = this.startTest.bind(this);
  }

  ngOnInit(): void {
    this.loadTestList();

    this.testListService.testSelected.subscribe((test: string) => {
      this.handleTestSelected(test);
    });

    this.testRunService.testRunEnded.subscribe((testResult: TestResult) => {
      this.endTest(testResult);
    });
  }

  /** Get test list from `testListService`. */
  loadTestList(): void {
    this.tests = this.testListService.getTestList();
  }

  startTest(args: object): void {
    const test = this.testListService.getCurrentTest();

    const factory = this.componentFactoryResolver.resolveComponentFactory(
        this.tests[test].component);
    const viewContainerRef = this.testLoader.viewContainerRef;
    viewContainerRef.clear();

    const componentRef = viewContainerRef.createComponent(factory);
    const testCase = componentRef.instance;

    try {
      try {
        testCase.setUp(args);
        testCase.runTest();
      } finally {
        testCase.tearDown();
      }
    } catch (error) {
      console.log(`${testCase.getTestName()} Failed`);
      console.log(`error: ${error}`);
    }

    this.testState = 'ACTIVE';
  }

  endTest(testResult: {[key: string]: any}): void {
    let log = '';
    if (testResult.success) {
      log = `Passed the ${this.testListService.getCurrentTest()} test`;
    } else {
      log = `Failed the ${this.testListService.getCurrentTest()} test`;
    }
    if (testResult.message) {
      log += `, ${testResult.message}`;
    }
    this.logs.push(log);
    this.testListService.clearCurrentTest();
    this.currentArgsSpec = [];
    this.testState = 'IDLE';
  }

  /** Handle the `testSelected` event. */
  private handleTestSelected(test: string): void {
    console.log(`loading test: ${test}`);

    this.currentArgsSpec = this.tests[test].argsSpec;

    this.testState = 'SETUP';
  }
}
