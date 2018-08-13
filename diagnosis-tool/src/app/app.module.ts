/* Copyright 2018 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
import {NgModule} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {BrowserModule} from '@angular/platform-browser';

import {AppComponent} from './app.component';
import {TestListService} from './test-list.service';
import {TestListComponent} from './test-list/test-list.component';
import {TestSettingComponent} from './test-setting/test-setting.component';
import {TestDirective} from './test.directive';
import {AudioComponent} from './tests/audio/audio.component';
import {DisplayComponent} from './tests/display/display.component';
import {TouchscreenComponent} from './tests/touchscreen/touchscreen.component';

/** The main application module. */
@NgModule({
  declarations: [
    AppComponent, TestListComponent, AudioComponent, TestDirective,
    DisplayComponent, TestSettingComponent, TouchscreenComponent
  ],
  imports: [BrowserModule, FormsModule],
  providers: [TestListService],
  bootstrap: [AppComponent],
  entryComponents: [AudioComponent, DisplayComponent, TouchscreenComponent]
})
export class AppModule {
}
