#include <PinChangeInterrupt.h>
#include <Servo.h>

#define CH1 A0  // 좌우 조향
#define CH2 A1  // 전후 구동

void handleCH1();
void handleCH2();

volatile int ch1Pulse = 1500;
volatile int ch2Pulse = 1500;

volatile unsigned long ch1Start = 0;
volatile unsigned long ch2Start = 0;

Servo frontServo;  // 앞바퀴 조향
Servo rearServo;   // 뒷바퀴 구동

unsigned long lastCheck = 0;
const unsigned long interval = 10;

const int FILTER_SIZE = 5;
int ch1Buffer[FILTER_SIZE] = {1500, 1500, 1500, 1500, 1500};
int ch2Buffer[FILTER_SIZE] = {1500, 1500, 1500, 1500, 1500};
int bufferIndex = 0;

int average(int* buffer) {
  long sum = 0;
  for (int i = 0; i < FILTER_SIZE; i++) {
    sum += buffer[i];
  }
  return sum / FILTER_SIZE;
}

void setup() {
  Serial.begin(9600);
  pinMode(CH1, INPUT_PULLUP);
  pinMode(CH2, INPUT_PULLUP);

  attachPCINT(digitalPinToPCINT(CH1), handleCH1, CHANGE);
  attachPCINT(digitalPinToPCINT(CH2), handleCH2, CHANGE);

  frontServo.attach(9);  // 조향
  rearServo.attach(10);  // 추진
}

void loop() {
  unsigned long now = millis();
  if (now - lastCheck >= interval) {
    lastCheck = now;

    // 이동 평균 필터 적용
    noInterrupts();
    ch1Buffer[bufferIndex] = ch1Pulse;
    ch2Buffer[bufferIndex] = ch2Pulse;
    interrupts();

    bufferIndex = (bufferIndex + 1) % FILTER_SIZE;

    int ch1Filtered = average(ch1Buffer);
    int ch2Filtered = average(ch2Buffer);

    // ▶ 앞바퀴 실시간 조향 (좌:1800, 우:900)
    int rawSteer = constrain(ch1Filtered, 900, 1800);
    int frontAngle = map(rawSteer, 900, 1800, 45, 135);
    frontAngle = constrain(frontAngle, 45, 135);
    frontServo.write(frontAngle);  // 실시간 반영

    // ▶ 뒷바퀴 전진/후진
    int rearAngle = 90;
    if (ch2Filtered > 1500) {
      rearAngle = 99;  // 느린 전진
    } else if (ch2Filtered < 1480) {
      rearAngle = 84;  // 느린 후진
    }
    rearServo.write(rearAngle);  // 항상 갱신

    // 디버깅 출력
    Serial.print("CH1: "); Serial.print(ch1Filtered);
    Serial.print(" | CH2: "); Serial.print(ch2Filtered);
    Serial.print(" | FrontAngle: "); Serial.print(frontAngle);
    Serial.print(" | RearAngle: "); Serial.println(rearAngle);
  }
}

void handleCH1() {
  if (digitalRead(CH1) == HIGH)
    ch1Start = micros();
  else if (ch1Start) {
    ch1Pulse = micros() - ch1Start;
    ch1Start = 0;
  }
}

void handleCH2() {
  if (digitalRead(CH2) == HIGH)
    ch2Start = micros();
  else if (ch2Start) {
    ch2Pulse = micros() - ch2Start;
    ch2Start = 0;
  }
}
