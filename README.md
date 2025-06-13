# 🚗 라인트래킹 자동차 시스템 (Raspberry Pi & Arduino)

본 프로젝트는 라즈베리파이와 아두이노를 이용하여 실시간 영상 기반의 라인트래킹 자동차를 구현하는 것을 목표로 합니다. 라즈베리파이는 카메라 영상을 획득하고 처리하여 라인을 검출하고 주행 방향을 결정하며, 이를 기반으로 아두이노에 조향 및 구동 명령을 전달합니다. 아두이노는 RC 신호 입력 처리 및 라즈베리파이로부터 받은 제어 명령을 기반으로 실제 자동차의 조향과 속도를 제어합니다. 웹 기반의 실시간 스트리밍과 상태 모니터링 시스템을 통해 사용자 친화적인 원격 제어 환경을 제공합니다.

유튜브 동작 영상 : https://www.youtube.com/shorts/V9vbhLZwnFo

---

## 👥 팀 구성원

|  이름  | 담당 업무                                                                      |
| ----- | -------------------------------------------------------------------------- |
| 윤석권 | 아두이노: RC 신호 입력 처리, 서보모터 및 ESC 제어, 라즈베리파이와의 UART 통신 구현                      |
| 유태영 | 라즈베리파이: 카메라 영상 캡처 및 처리, 라인 인식 알고리즘 구현, 웹 대시보드 및 스트리밍 구현, 아두이노와의 UART 통신 구현 |

---

## 📍 아두이노 핀 구성 요약

| 기능                    | 핀 번호   | 설명             |
| --------------------- | ------ | -------------- |
| 조향 서보 PWM 출력          | Pin 9  | 조향 서보 제어       |
| 전진/후진 PWM 출력 (ESC)    | Pin 10 | ESC(모터) 제어용    |
| RC 수신기 조향 입력 (CH1)    | A0     | RC 수신기의 CH1 연결 |
| RC 수신기 전진/후진 입력 (CH2) | A1     | RC 수신기의 CH2 연결 |
| 방향 지시등 (좌측)           | Pin 7  | 좌회전 시 LED 점등   |
| 방향 지시등 (우측)           | Pin 8  | 우회전 시 LED 점등   |
| 자동/수동 모드 전환 스위치       | A02 | ch9와 연결   |

---
## 📍 rc카 구성
| ![image](images/up.png) | ![image](images/front.png) | ![image](images/right.png) | ![image](images/led.png) |
| :---------------------: | :----------------------: | :-----------------------: | :---------------------: |
| 상단(Top View)     | 앞  (Front View)    | 옆  (Side View)   | 후방 LED(Rear LED Indicator) |

## 📂 소스별 동작 요약

### ✅ 라즈베리파이 `main.py`

| 단계       | 기능 요약                                            |
| -------- | ------------------------------------------------ |
| 카메라 초기화  | `Picamera2` 320×240 @≈100 Hz 캡처                  |
| 영상 전처리   | Gray → GaussianBlur → Threshold(BINARY\_INV)     |
| ROI 설정   | 프레임 하단 60 – 75 % 영역만 검사                          |
| 라인 위치 계산 | `findContours` + `moments` → 중심(cₓ) 산출           |
| 방향 판정    | 5단계 (LEFT\_HARD/LEFT/STRAIGHT/RIGHT/RIGHT\_HARD) |
| 명령 송신    | 시리얼 문자 전송 & WebSocket JPEG 스트림 배포                |
---

## 🖼️ 이미지 처리 · 라인트레이싱 제어

### 1️⃣ 전처리 & ROI 설정

* **흑백 변환 → 가우시안 블러 → 역이진화**로 노이즈를 최소화하고 라인을 선명하게 추출합니다.
* 해상도 320×240 중 \*\*하단 15 % (60 – 75 %)\*\*만 관심 영역(ROI)으로 삼아 계산량을 줄이고 오검출을 방지합니다.

### 2️⃣ 라인 검출 및 중심 좌표 계산

* `cv2.findContours`로 ROI 안의 흰색 객체(라인)를 모두 찾습니다.
* **최대 면적** 컨투어를 실제 주행 라인으로 간주하고, `cv2.moments`로 **무게중심(cₓ)** 을 계산합니다.

### 3️⃣ 방향 결정 로직 (5‑State FSM)

| 구간 경계                  | 방향 상태           |
| ---------------------- | --------------- |
| `cₓ < 0.25·W`          | **LEFT\_HARD**  |
| `0.25·W ≤ cₓ < 0.40·W` | **LEFT**        |
| `0.40·W ≤ cₓ ≤ 0.60·W` | **STRAIGHT**    |
| `0.60·W < cₓ ≤ 0.75·W` | **RIGHT**       |
| `cₓ > 0.75·W`          | **RIGHT\_HARD** |

> HARD/Soft 2‑레벨 분류로 미세 조향과 급조향을 구분해 드리프트를 최소화합니다.

### 4️⃣ 시리얼 명령 매핑

| 상태          | 기본 가속 | 조향 문자 |
| ----------- | ----- | ----- |
| STRAIGHT    | `f`   | `s`   |
| LEFT        | `f`   | `l`   |
| RIGHT       | `f`   | `r`   |
| LEFT\_HARD  | `f`   | `L`   |
| RIGHT\_HARD | `f`   | `R`   |

* **중복 전송 차단**: 직전 전송 문자와 동일하면 생략해 UART 대역폭 절약.
* **ESC 가속 유지**: 매 주기 `f`(가속 유지) → 스티어링 문자 순으로 전송.

### 5️⃣ 라인 유실 복구 전략

1. 라인이 ‘NO LINE’으로 판정되면 **1회만** 복구 루틴 실행.
2. 직전 논리 방향이 좌측이면 우측(`r`)으로 반대 방향 휙 꺾기, 우측이면 좌측(`l`) 반전.
3. 짧은 후진(`b`)으로 라인을 재검색 → 라인 복구 시 정상 FSM 복귀.

### 🔑 핵심 파라미터

| 항목        | 기본값                           | 비고                        |
| --------- | ----------------------------- | ------------------------- |
| Threshold | 150                           | 조명·노면에 따라 120 – 180 범위 권장 |
| ROI (%)   | 60 – 75                       | 노면만 집중, 필요 시 50 – 80 재조정  |
| FSM 경계    | 0.25 / 0.40 / 0.60 / 0.75 · W | 차량 폭·카메라 FOV에 맞춰 조절       |
| 주기        | 10 ms                         | ≈100 Hz 처리 목표 (RPi 4 기준)  |


### 📄 발췌 코드 (요약)

```python
# === 전처리 ===
gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
gray  = cv2.GaussianBlur(gray, (5, 5), 0)
_, bin = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
roi   = bin[int(HEIGHT*0.60): int(HEIGHT*0.75), :]

# === 라인 검출 ===
contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
latest_direction = "NO LINE"
if contours:
    M = cv2.moments(max(contours, key=cv2.contourArea))
    if M["m00"]:
        cx = int(M["m10"] / M["m00"])
        # FSM 분기 (상세 표 참고)
```
 
 ## 🔗 라즈베리파이 ↔ 아두이노 통신 프로토콜

### 📡 통신 개요

- **방식**: UART Serial (9600 bps, 8N1)
- **하드웨어 연결**: Raspberry Pi USB 포트 ↔ Arduino USB 포트 (USB-Serial 통신)
- **프로토콜 구조**:  
  - Raspberry Pi → Arduino: **단일 문자 명령어 전송**  
  - Arduino → Raspberry Pi: **단일 문자 상태 피드백 전송**

### 📤 Raspberry Pi → Arduino 명령어

| 명령 문자 | 의미                   | 동작 내용                                      |
| ---------- | ---------------------- | -------------------------------------------- |
| `f`        | 전진(Forward) 유지 명령    | ESC 가속 유지                                 |
| `s`        | 직진 조향(STRAIGHT)     | 조향을 중앙으로 유지                          |
| `l`        | 좌회전(LEFT)            | 서보를 좌회전 방향으로 제어                   |
| `L`        | 급좌회전(LEFT_HARD)     | 서보를 급좌 방향으로 제어                     |
| `r`        | 우회전(RIGHT)           | 서보를 우회전 방향으로 제어                   |
| `R`        | 급우회전(RIGHT_HARD)    | 서보를 급우 방향으로 제어                     |
| `b`        | 후진(Backward)          | ESC를 후진 방향으로 제어                      |
| `a`        | 자율주행 모드 시작 요청   | Arduino가 자율주행 상태로 진입, 상태 피드백 전송 |
| `n`        | 수동 모드로 전환 요청    | Arduino가 수동 상태로 복귀, 상태 피드백 전송    |

### 📥 Arduino → Raspberry Pi 상태 피드백

| 문자 | 의미                        |
| ----- | -------------------------- |
| `a`   | Arduino가 **자율주행 모드 활성화됨** |
| `n`   | Arduino가 **수동 모드 활성화됨**    |

### 📈 통신 흐름 예시

1. Raspberry Pi → 'a' 전송 → Arduino 자율주행 모드 진입 → 'a' 응답 수신
2. Raspberry Pi → 'f' + 방향문자(l/r/s 등) 주기적 전송 → Arduino 실시간 차량 제어
3. Raspberry Pi → 필요 시 'n' 전송 → Arduino 수동 모드 복귀 → 'n' 응답 수신

### ✅ 주요 함수 구성

- `find_arduino_port()`: 연결 가능한 Arduino 포트 자동 탐색 및 시리얼 연결 초기화
- `analyze_direction(frame)`: OpenCV 기반 라인 검출 → 중심좌표(cₓ)에 따라 진행 방향 결정 (`latest_direction` 업데이트)
- `camera_loop()`: Picamera2 프레임 캡처 및 분석 → 방향 명령 시리얼 전송 + WebSocket용 JPEG 프레임 저장 (비동기 coroutine)
- `send_serial(code)`: Arduino로 단일 문자 명령 전송 + 로그 기록
- `serial_read_loop()`: Arduino로부터 자율주행/수동 모드 상태 피드백 수신 및 반영 (비동기 coroutine)
- `handle_client(websocket)`: 접속 클라이언트에 실시간 JPEG 스트림 전송 (WebSocket 기반)
- `StatusHandler`: HTTP API(`/status`, `/mode`, `/arduino`, `/serial-log`) 제공

###
## 📂 소프트웨어
- **PlatformIO** 개발 환경 (VSCode 통합)
- **사용 라이브러리**
  - `PinChangeInterrupt` - RC 수신기 PWM 신호 디코딩용
  - `Servo` - 서보 제어

## 🚘 아두이노 동작 개요

### 1. **수동 모드**
- **CH1 (좌우 핸들)**: 900 - 1800 범위 입력 → 앞바퀴 서보 각도 45~135도로 변환
- **CH2 (전후 주행)**: 
  - 1500us: 정지
  - 1582us: 전진
  - 1430us: 후진
- **LED 시그널**
  - 후진 시: 양쪽 LED 고정 점등
  - 좌회전: 왼쪽 LED 깜빡임
  - 우회전: 오른쪽 LED 깜빡임

### 2. **오토 모드**
- **시리얼 명령 제어**
  - `'f'`: 전진
  - `'b'`: 후진
  - `'t'`: 중립
  - `'s'`: 조향 정지 (90도)
  - `'l'`: 작은 좌회전 (120도)
  - `'r'`: 작은 우회전 (70도)
  - `'L'`: 큰 좌회전 (135도)
  - `'R'`: 큰 우회전 (45도)
- **LED 시그널**: 수동 모드와 동일한 조건으로 제어

### 3. **모드 전환**
- **CH9 PWM 신호가 변할 때마다 수동/오토 모드 전환**
- 또는 시리얼 명령 `'A'`(Auto), `'N'`(Normal)로도 모드 전환 가능
- 전환 시 `"a"` 또는 `"n"`이 시리얼로 출력되어 상태 확인 가능

## 4.🧠 메인 코드 설명

### ▶️ 모드 전환 로직
RC 수신기의 CH9 채널이 위/아래로 바뀔 때마다 수동 ↔ 자동 모드가 토글되며, 동시에 시리얼 출력도 함께 발생합니다.

```cpp
if ((lastCh9Pulse <= 1500 && ch9Pulse > 1500) || (lastCh9Pulse > 1500 && ch9Pulse <= 1500)) {
  autonomousMode = !autonomousMode;
  Serial.println(autonomousMode ? "a" : "n");
}
lastCh9Pulse = ch9Pulse;
````

또한 시리얼 명령 `A`, `N`을 통해서도 강제로 오토/노말 모드로 진입할 수 있습니다.

```cpp
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
```

---

### 🕹 수동 모드 (CH1/CH2 기반)

## 🔄 PWM 입력 필터링 및 조향 제어 (수동 모드)
```cpp
noInterrupts();
ch1Buffer[bufferIndex] = ch1Pulse;
ch2Buffer[bufferIndex] = ch2Pulse;
interrupts();
```

* **RC 신호 안정성 확보**:

  * `ch1Pulse`와 `ch2Pulse`는 인터럽트에서 실시간으로 업데이트되는 변수입니다.
  * `noInterrupts()`와 `interrupts()` 사이에서만 값을 읽음으로써, **중간에 값이 바뀌는 것을 방지**합니다.
  * 이로써 버퍼에 항상 **정확한 PWM 값**이 들어갑니다.


조향 및 속도 입력은 `FILTER_SIZE` 크기의 버퍼를 평균내어 필터링합니다. 이로써 조작이 부드러워집니다.


---

```cpp
bufferIndex = (bufferIndex + 1) % FILTER_SIZE;
int ch1Filtered = average(ch1Buffer);
int ch2Filtered = average(ch2Buffer);
```

* **소프트웨어 필터링**:

  * 최근 `FILTER_SIZE`만큼의 값을 \*\*순환 버퍼(Ring buffer)\*\*에 저장합니다.
  * `average()` 함수는 최근 N개의 PWM 값을 평균 내어, **신호의 순간적인 잡음이나 튐을 완화**합니다.

---

```cpp
int steer = constrain(ch1Filtered, 900, 1800);
int angle = map(steer, 900, 1800, 45, 135);
angle = constrain(angle, 45, 135);
frontServo.write(angle);
```

* **조향 신호 해석 및 서보 출력**:

  * `steer`는 수신된 PWM을 제한된 범위(900\~1800)로 자릅니다.
  * `map()` 함수는 PWM을 서보의 조향각 범위(45\~135도)로 선형 변환합니다.
  * `constrain()`을 한 번 더 써서 혹시라도 `map()` 계산 결과가 넘치는 것을 방지합니다.
  * 최종적으로 `frontServo.write(angle)` 명령을 통해 **앞바퀴 조향 서보를 회전시킵니다**.

---

속도 제어는 다음과 같이 임계값 기준으로 후진, 정지, 전진을 구분합니다.

```cpp
if (ch2Filtered > 1510) {
  drive = 1582;
} else if (ch2Filtered < 1460) {
  drive = 1430;
} else {
  drive = 1500;
}
rearServo.writeMicroseconds(drive);
```

### 💡 수동 모드 LED 제어

```cpp
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
```

* `drive < 1464`: CH2(전후 입력)이 일정 기준 이하일 경우 → **후진으로 판단**
* `angle > 100` 또는 `< 80`: CH1(좌우 입력)을 기반으로 **조향각이 큰 경우** → 회전으로 판단
* `millis() % 400 < 200`: 0.4초 주기로 깜빡임 구현 (200ms ON / 200ms OFF)

이러한 조건 분기로 인해 **방향등 / 후진등 동작**을 구현합니다.

---

### 🤖 오토 모드 (시리얼 명령 기반)

시리얼로 조향 및 구동 명령을 수신하여 즉시 반영합니다.

```cpp
if (cmd == 'l') frontServo.write(120);
if (cmd == 'r') frontServo.write(70);
if (cmd == 'L') frontServo.write(135);
if (cmd == 'R') frontServo.write(45);
if (cmd == 's') frontServo.write(90);

if (cmd == 'f') lastRearCmd = 'f';
if (cmd == 'b') lastRearCmd = 'b';
if (cmd == 't') lastRearCmd = 't';
```


```cpp
if (lastRearCmd == 'f') {
  rearServo.writeMicroseconds(1558);
} else if (lastRearCmd == 'b') {
  rearServo.writeMicroseconds(1430);
} else {
  rearServo.writeMicroseconds(1500);
}
```

### 📡 오토모드 명령어 설명

| 명령어 | 기능 설명            | 조향/구동 | 적용 시 동작                         |
|--------|----------------------|-----------|--------------------------------------|
| `l`    | 부드러운 좌회전      | 조향      | 조향각 약 120도로 작은 좌회전     |
| `r`    | 부드러운 우회전      | 조향      | 조향각 약 70도로 작은 우회전      |
| `L`    | 급격한 좌회전        | 조향      | 조향각 135도, 큰 좌회전           |
| `R`    | 급격한 우회전        | 조향      | 조향각 45도, 큰 우회전            |
| `s`    | 직진 (조향 정지)     | 조향      | 조향각 90도로 중앙 정렬             |
| `f`    | 전진                 | 구동      | rear 서보 1558μs → 전진             |
| `b`    | 후진                 | 구동      | rear 서보 1430μs → 후진             |
| `t`    | 정지 (throttle 중립) | 구동      | rear 서보 1500μs → 정지 상태 유지   |

```cpp
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
```

#### ✅LED의 오토 모드에서의 차이점
오토모드 led제어입니다
오토 모드에서도 수동과 **동일한 LED 제어 로직**이 적용됩니다. 단, 시리얼 명령을 기준으로 `lastRearCmd`, `lastFrontCmd` 상태값을 기준으로 판단:
* RC 수신기 값이 아닌 **시리얼 명령(`'l'`, `'r'`, `'b'` 등)** 으로 상태 판단
* LED는 이전에 입력된 명령을 `lastRearCmd`/`lastFrontCmd`에 저장해 기반으로 동작
* 조향 명령이 없을 때는 LED가 꺼져 있어 **방향 표시가 명확히 드러남**

---
---

## 📡 PWM 신호 측정: `handleCHx()` 함수 설명

이 세 함수는 각각 \*\*CH1 (조향), CH2 (주행), CH9 (모드 전환)\*\*의 PWM 신호를 측정하여 `ch1Pulse`, `ch2Pulse`, `ch9Pulse` 변수에 마이크로초(us) 단위로 저장합니다.

### ✨ 공통 구조

```cpp
if (digitalRead(CHx) == HIGH) {
  chxStart = micros();  // 상승 에지에서 시간 기록
} else if (chxStart) {
  chxPulse = micros() - chxStart;  // 하강 에지에서 펄스 폭 계산
  chxStart = 0;                    // 측정 완료 후 초기화
}
```

---

### 📌 작동 원리 요약

| 순서 | 상태       | 동작 내용                                 |
| -- | -------- | ------------------------------------- |
| ①  | 상승 에지    | `digitalRead()`가 `HIGH` → 시작 시간 기록    |
| ②  | 하강 에지    | `digitalRead()`가 `LOW` → 펄스 폭 계산 및 저장 |
| ③  | 완료 후 초기화 | `chxStart = 0`으로 다음 측정을 준비함           |

---

