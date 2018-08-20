import {Component, OnInit} from '@angular/core';
import {TestCase} from '../../interfaces/test-case';
import {TestRunService} from '../../test-run-service';

type TestScreenState = 'SHOW'|'HIDE';

@Component({
  selector: 'app-display-point',
  templateUrl: './display-point.component.html',
  styleUrls: ['./display-point.component.css']
})
export class DisplayPointComponent extends TestCase implements OnInit {
  constructor(private readonly testRunService: TestRunService) {
    super();
    this.keyDown = this.keyDown.bind(this);
  }

  args: {[key: string]: number} = {};
  testIndex: number = 0;
  dotArray: {style: {[key: string]: any}}[] = [];
  testScreenState: TestScreenState = 'HIDE';

  ngOnInit(): void {}

  setUp(args: {[key: string]: number}) {
    // TODO(b/111100698): check it's limit in args spec
    args.max_point_count = Math.min(9, args.max_point_count);
    this.args = args;
    this.init();
  }

  runTest(): void {
    console.log(`${this.getTestName()}.runTest is called`);
  }

  endTest(success: boolean, message: string): void {
    document.removeEventListener('keydown', this.keyDown);
    this.testRunService.endTest(success, message);
  }

  keyDown(e?: KeyboardEvent, key?: string): void {
    let code = e ? e.key : key;
    if (code) {
      code = code.toLowerCase();
    } else {
      return;
    }
    if (code === 'space' || code === ' ') {
      this.setupDisplay(this.testScreenState === 'HIDE' ? 'SHOW' : 'HIDE');
    } else if (code === 'escape') {
      this.endTest(false, 'Aborted by user');
    } else if (code >= '1' && code <= this.args.max_point_count.toString()) {
      if (parseInt(code) === this.dotArray.length) {
        this.testIndex++;
        this.setupDisplay('SHOW');
        this.setupDots();
      } else {
        this.endTest(
            false,
            `Correct answer: ${this.dotArray.length}, your answer: ${code}`);
      }
    }
    if (e) {
      e.preventDefault();
    }
  }

  isCollision(posX: number, posY: number, radius: number): boolean {
    for (let i = 0; i < this.dotArray.length; i++) {
      const centerX = this.dotArray[i].style.left.slice(0, -2) +
          this.dotArray[i].style.width.slice(0, -2) * 0.5;
      const centerY = this.dotArray[i].style.top.slice(0, -2) +
          this.dotArray[i].style.height.slice(0, -2) * 0.5;
      if (Math.pow(posX + radius - centerX, 2) +
              Math.pow(posY + radius - centerY, 2) <=
          10 * 10) {
        return true;
      }
    }
    return false;
  }

  setupDots(): void {
    const backgroundColor = this.testIndex == 0 ? 'white' : 'black';
    const foregroundColor = this.testIndex == 0 ? 'black' : 'white';
    let screen = document.getElementById('test');
    if (!screen) {
      return;
    }
    if (this.testIndex >= 2) {
      this.endTest(true, '');
      return;
    }
    screen.style.backgroundColor = backgroundColor;
    this.dotArray = [];
    const number = Math.floor(Math.random() * this.args.max_point_count) + 1;
    for (let i = 0; i < number; i++) {
      let posX = Math.random() * window.innerWidth;
      let posY = Math.random() * window.innerHeight;
      while (this.isCollision(posX, posY, this.args.point_size * 0.5)) {
        posX = Math.random() * window.innerWidth;
        posY = Math.random() * window.innerHeight;
      }
      this.dotArray.push({
        style: {
          position: 'absolute',
          top: posY + 'px',
          left: posX + 'px',
          width: this.args.point_size + 'px',
          height: this.args.point_size + 'px',
          borderRadius: '50%',
          backgroundColor: foregroundColor,
          display: 'block'
        }
      });
    }
  }

  setupDisplay(state?: TestScreenState): void {
    let screen = document.getElementById('test');
    if (!screen) {
      return;
    }
    if (state) {
      this.testScreenState = state;
    }
    for (let i = 0; i < this.dotArray.length; i++) {
      this.dotArray[i].style.display =
          this.testScreenState === 'SHOW' ? 'block' : 'none';
    }
  }

  clickButton(event: Event, key: string): void {
    if (key === 'Mark Failed') {
      this.endTest(false, 'you mark failed');
      return;
    }
    this.keyDown(undefined, key);
    event.preventDefault();
  }

  getButtons(): string[] {
    let buttons = ['SPACE', 'ESCAPE'];
    for (let i = 1; i <= this.args.max_point_count; i++) {
      buttons.push(i.toString());
    }
    buttons.push('Mark Failed');
    return buttons;
  }

  getTestName(): string {
    return 'DisplayPoint';
  }

  init(): void {
    document.addEventListener('keydown', this.keyDown);
    this.testIndex = 0;
    this.setupDots();
    this.setupDisplay('HIDE');
  }
}

export const DISPLAYPOINT_ARGS_SPEC = [
  {
    name: 'point_size',
    help: 'width and height of testing point in px.',
    default: 3.0,
    type: 'number'
  },
  {
    name: 'max_point_count',
    help: 'maximum number of points in each subtest.',
    default: 5,
    type: 'number'
  }
];
