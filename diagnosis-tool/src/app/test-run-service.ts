import {EventEmitter, Injectable} from '@angular/core';

@Injectable()
export class TestRunService {
  testRunEnded: EventEmitter<TestResult> = new EventEmitter();

  constructor() {}

  endTest(success: boolean, message: string) {
    this.testRunEnded.emit({
      success,
      message
    });
  }
}

export interface TestResult {
  success: boolean;
  message: string;
};