#include <PinChangeInterrupt.h>
#include <Servo.h>

#define CH1 A0
#define CH2 A1
#define CH9 A2

#define LEFT_LED_PIN 6
#define RIGHT_LED_PIN 7

void handleCH1();
void handleCH2();
void handleCH9();

volatile int ch1Pulse = 1500;
volatile int ch2Pulse = 1500;
volatile int ch9Pulse = 1000;

volatile unsigned long ch1Start = 0;
volatile unsigned long ch2Start = 0;
volatile unsigned long ch9Start = 0;

Servo frontServo;
Servo rearServo;

unsigned long lastCheck = 0;
const unsigned long interval = 10;

const int FILTER_SIZE = 5;
int ch1Buffer[FILTER_SIZE] = {1500, 1500, 1500, 1500, 1500};
int ch2Buffer[FILTER_SIZE] = {1500, 1500, 1500, 1500, 1500};
int bufferIndex = 0;

bool autonomousMode = false;
int lastCh9Pulse = 1500;

int average(int* buffer) {
  long sum = 0;
  for (int i = 0; i < FILTER_SIZE; i++) sum += buffer[i];
  return sum / FILTER_SIZE;
}

void setup() {
  Serial.begin(9600);
  pinMode(CH1, INPUT_PULLUP);
  pinMode(CH2, INPUT_PULLUP);
  pinMode(CH9, INPUT_PULLUP);
  pinMode(LEFT_LED_PIN, OUTPUT);
  pinMode(RIGHT_LED_PIN, OUTPUT);

  attachPCINT(digitalPinToPCINT(CH1), handleCH1, CHANGE);
  attachPCINT(digitalPinToPCINT(CH2), handleCH2, CHANGE);
  attachPCINT(digitalPinToPCINT(CH9), handleCH9, CHANGE);

  frontServo.attach(9);
  rearServo.attach(10);
}

void loop() {
  unsigned long now = millis();
  if (now - lastCheck >= interval) {
    lastCheck = now;

    // CH9 신호 변화 감지 → 모드 토글
    if ((lastCh9Pulse <= 1500 && ch9Pulse > 1500) || (lastCh9Pulse > 1500 && ch9Pulse <= 1500)) {
      autonomousMode = !autonomousMode;
      Serial.println(autonomousMode ? "a" : "n");
    }
    lastCh9Pulse = ch9Pulse;

    // 시리얼 명령 처리 (모드 전환 + 오토 동작)
    static char lastRearCmd = 'f';
    static char lastFrontCmd = 's';

    while (Serial.available()) {
      char cmd = Serial.read();

      // 모드 강제 전환
      if (cmd == 'A') {
        if (!autonomousMode) {
          autonomousMode = true;
          Serial.println("a");
        }
      } else if (cmd == 'N') {
        if (autonomousMode) {
          autonomousMode = false;
          Serial.println("n");
        }
      }

      // 오토모드 명령 처리
      if (autonomousMode) {
        if (cmd == 'l') {
          frontServo.write(120);
          lastFrontCmd = cmd;
        } else if (cmd == 'r') {
          frontServo.write(70);
          lastFrontCmd = cmd;
        }if (cmd == 'L') {
          frontServo.write(135);
          lastFrontCmd = cmd;
        } else if (cmd == 'R') {
          frontServo.write(45);
          lastFrontCmd = cmd;
        } else if (cmd == 's') {
          frontServo.write(90);
          lastFrontCmd = cmd;
        } else if (cmd == 'f' || cmd == 'b' || cmd == 't') {
          lastRearCmd = cmd;
        }
      }
    }

    // 오토모드 동작
    if (autonomousMode) {
      if (lastRearCmd == 'f') {
        rearServo.writeMicroseconds(1558);
      } else if (lastRearCmd == 'b') {
        rearServo.writeMicroseconds(1430);
      } else {
        rearServo.writeMicroseconds(1500);
      }

      // LED 제어
      if (lastRearCmd == 'b') {
        digitalWrite(LEFT_LED_PIN, HIGH);
        digitalWrite(RIGHT_LED_PIN, HIGH);
      } else if (lastFrontCmd == 'l') {
        digitalWrite(LEFT_LED_PIN, millis() % 400 < 200 ? HIGH : LOW);
        digitalWrite(RIGHT_LED_PIN, LOW);
      } else if (lastFrontCmd == 'r') {
        digitalWrite(RIGHT_LED_PIN, millis() % 400 < 200 ? HIGH : LOW);
        digitalWrite(LEFT_LED_PIN, LOW);
      } else {
        digitalWrite(LEFT_LED_PIN, LOW);
        digitalWrite(RIGHT_LED_PIN, LOW);
      }

      return;
    }

    // 수동모드
    noInterrupts();
    ch1Buffer[bufferIndex] = ch1Pulse;
    ch2Buffer[bufferIndex] = ch2Pulse;
    interrupts();

    bufferIndex = (bufferIndex + 1) % FILTER_SIZE;
    int ch1Filtered = average(ch1Buffer);
    int ch2Filtered = average(ch2Buffer);

    int steer = constrain(ch1Filtered, 900, 1800);
    int angle = map(steer, 900, 1800, 45, 135);
    angle = constrain(angle, 45, 135);
    frontServo.write(angle);

    int drive = 1500;
    if (ch2Filtered > 1510) {
      drive = 1582;
    } else if (ch2Filtered < 1460) {
      drive = 1430;
    } else {
      drive = 1500;
    }
    rearServo.writeMicroseconds(drive);

    // 수동 LED 제어
    if (drive < 1464) {
      digitalWrite(LEFT_LED_PIN, HIGH);
      digitalWrite(RIGHT_LED_PIN, HIGH);
    } else if (angle > 100) {
      digitalWrite(LEFT_LED_PIN, millis() % 400 < 200 ? HIGH : LOW);
      digitalWrite(RIGHT_LED_PIN, LOW);
    } else if (angle < 80) {
      digitalWrite(RIGHT_LED_PIN, millis() % 400 < 200 ? HIGH : LOW);
      digitalWrite(LEFT_LED_PIN, LOW);
    } else {
      digitalWrite(LEFT_LED_PIN, LOW);
      digitalWrite(RIGHT_LED_PIN, LOW);
    }
  }
}

void handleCH1() {
  if (digitalRead(CH1) == HIGH) ch1Start = micros();
  else if (ch1Start) {
    ch1Pulse = micros() - ch1Start;
    ch1Start = 0;
  }
}

void handleCH2() {
  if (digitalRead(CH2) == HIGH) ch2Start = micros();
  else if (ch2Start) {
    ch2Pulse = micros() - ch2Start;
    ch2Start = 0;
  }
}

void handleCH9() {
  if (digitalRead(CH9) == HIGH) ch9Start = micros();
  else if (ch9Start) {
    ch9Pulse = micros() - ch9Start;
    ch9Start = 0;
  }
}
