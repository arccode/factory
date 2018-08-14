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
import {TestDirective} from './test.directive';

type TestState = 'IDLE' | 'SETUP' | 'ACTIVE';

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

  log: string = '';

  currentArgsSpec: ArgSpec[] = [];

  testState: TestState = 'IDLE';

  /** Directive to load a test case. */
  @ViewChild(TestDirective) testLoader!: TestDirective;

  constructor(
      private readonly testListService: TestListService,
      private readonly componentFactoryResolver: ComponentFactoryResolver) {}

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

  startTest =
      (args: object) => {
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

  /** Handle the `testSelected` event. */
  private handleTestSelected(test: string): void {
    console.log(`loading test: ${test}`);

    this.currentArgsSpec = this.tests[test].argsSpec;

    this.testState = 'SETUP';
  }
}
