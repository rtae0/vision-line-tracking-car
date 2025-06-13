import asyncio          # 비동기 프로그래밍 (async/await)
import threading        # 스레딩 (HTTP 서버를 별도 스레드에서 실행)
import http.server      # HTTP 서버 구현
import socketserver     # TCP 서버용 socketserver
import os               # OS 관련 기능 (경로 등)
import cv2              # OpenCV (이미지 처리)
import time             # 시간 측정 및 sleep
import websockets       # WebSocket 서버 구현
import serial           # pySerial (시리얼 통신)
import glob             # 파일 경로 검색 (패턴 기반)
from picamera2 import Picamera2  # Raspberry Pi 카메라2 API

# 설정
WIDTH, HEIGHT = 320, 240  # 카메라 프레임 해상도 (너비, 높이)
clients = set()  # WebSocket 연결된 클라이언트 집합
latest_frame = None  # 최신 카메라 프레임 (JPEG 인코딩된 바이트)
latest_direction = "Initializing..."  # 현재 인식된 주행 방향 상태
auto_mode = False  # 자율주행 모드 상태 (ON/OFF)
lock = asyncio.Lock()  # 프레임 보호용 asyncio 락 (비동기 동시 접근 방지)
last_sent = None  # 아두이노로 마지막 전송한 시리얼 코드
serial_log = []  # 시리얼 통신 로그 (전송/수신 기록 저장)
prev_logical_direction = None  # 직전 논리적 주행 방향 (LEFT, RIGHT, STRAIGHT 등 기억용)

# 아두이노 포트 자동 탐색 및 시리얼 연결 함수
def find_arduino_port():
    # '/dev/ttyACM*' 패턴으로 연결 가능한 시리얼 포트 검색 (리눅스/Raspberry Pi 기준)
    for port in glob.glob('/dev/ttyACM*'):
        try:
            # 시리얼 포트 열기 (속도 9600 baud, timeout 1초)
            return serial.Serial(port, 9600, timeout=1)
        except:
            # 포트 오픈 실패 시 다음 포트 시도
            continue
    # 연결 가능한 포트가 없는 경우 None 반환
    return None

# 아두이노 시리얼 포트 연결 시도
ser = find_arduino_port()
if ser:
    print(f"✅ 아두이노 시리얼 연결 성공: {ser.port}")
else:
    print("⚠️ 아두이노 시리얼 연결 실패")

# 시리얼 명령 전송 함수
def send_serial(code):
    global ser, last_sent
    # 아두이노 시리얼 포트가 정상 연결/열려 있을 경우
    if ser and ser.is_open:
        try:
            # 시리얼로 문자열 코드 전송 (utf-8 인코딩)
            ser.write(code.encode('utf-8'))
            # 시리얼 로그에 전송 기록 추가 (시간 + 코드)
            serial_log.append(f"[{time.strftime('%H:%M:%S')}] {code}")
            # 콘솔에 전송 정보 출력
            print(f"📤 전송됨 → Arduino: {code}")
            # 마지막 전송한 코드 갱신
            last_sent = code
        except:
            # 전송 중 에러 발생 시 경고 출력
            print(f"⚠️ 시리얼 전송 실패 ({code})")

# HTTP 핸들러 클래스 (상태 확인용 API 제공)
class StatusHandler(http.server.SimpleHTTPRequestHandler):
    # HTTP GET 요청 처리
    def do_GET(self):
        # 현재 주행 방향 상태 반환
        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            # latest_direction 값 전송
            self.wfile.write(latest_direction.encode("utf-8"))

        # 자율주행 모드 상태 반환 (ON / OFF)
        elif self.path == "/mode":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(("ON" if auto_mode else "OFF").encode("utf-8"))

        # 아두이노 연결 상태 반환 (CONNECTED / DISCONNECTED)
        elif self.path == "/arduino":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            status = "CONNECTED" if ser and ser.is_open else "DISCONNECTED"
            self.wfile.write(status.encode("utf-8"))

        # 시리얼 통신 로그 반환 (최근 100줄)
        elif self.path == "/serial-log":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            # serial_log 리스트에서 최근 100줄만 선택
            log_text = "\n".join(serial_log[-100:])
            self.wfile.write(log_text.encode("utf-8"))

        # 그 외 요청은 기본 SimpleHTTPRequestHandler 처리
        else:
            super().do_GET()

    # HTTP POST 요청 처리
    def do_POST(self):
        global auto_mode
        # 자율주행 모드 토글 요청
        if self.path == "/autonomous":
            # 자율주행 모드가 OFF일 때만 초기 명령 'a' 전송
            if not auto_mode:
                send_serial('a')

            # 자율주행 모드 상태 반전 (ON <-> OFF)
            auto_mode = not auto_mode

            # 상태 변경 로그 출력
            print(f"🚀 자유주회 모드 전환됨: {'ON' if auto_mode else 'OFF'}")

            # 204 No Content 응답
            self.send_response(204)
            self.end_headers()
        else:
            # 잘못된 경로 요청 시 404 에러 반환
            self.send_error(404)
            
# HTTP 서버 실행 함수
def start_http_server():
    # 현재 실행 중인 파이썬 파일의 디렉토리로 작업 디렉토리 변경
    os.chdir(os.path.dirname(__file__))

    # TCP 서버 생성 (0.0.0.0:8001 포트에서 StatusHandler 사용)
    with socketserver.TCPServer(("", 8000), StatusHandler) as httpd:
        print("🌐 HTTP 서버 실행 중 (포트 8000)")
        # 서버 무한 루프 실행 (클라이언트 요청 대기)
        httpd.serve_forever()

# 라인 분석 함수 (카메라 프레임 분석 후 주행 방향 결정)
def analyze_direction(frame):
    global latest_direction

    # 1️⃣ 그레이스케일 변환 (흑백으로 변환)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # 2️⃣ 가우시안 블러 적용 (노이즈 제거)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # 3️⃣ 임계값 적용 → 바이너리 이미지 (흰색/검정)
    _, binary = cv2.threshold(blur, 150, 255, cv2.THRESH_BINARY_INV)

    # 4️⃣ ROI(Region of Interest, 관심 영역) 설정 → 화면 하단부 일부만 사용
    roi_top = int(HEIGHT * 0.60)
    roi_bottom = int(HEIGHT * 0.75)
    roi = binary[roi_top:roi_bottom, :]

    # 5️⃣ ROI에서 외곽선(Contours) 찾기
    contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 6️⃣ 외곽선이 존재하면 가장 큰 외곽선을 사용
    if contours:
        largest = max(contours, key=cv2.contourArea)

        # 7️⃣ 외곽선의 모멘트(중심점) 계산
        M = cv2.moments(largest)

        if M["m00"] != 0:
            # 중심 좌표 cx 계산
            cx = int(M["m10"] / M["m00"])

            # 8️⃣ cx 위치에 따라 방향 판단
            if cx < WIDTH * 0.25:
                latest_direction = "LEFT_HARD"  # 매우 왼쪽
            elif cx < WIDTH * 0.4:
                latest_direction = "LEFT"  # 약간 왼쪽
            elif cx > WIDTH * 0.75:
                latest_direction = "RIGHT_HARD"  # 매우 오른쪽
            elif cx > WIDTH * 0.6:
                latest_direction = "RIGHT"  # 약간 오른쪽
            else:
                latest_direction = "STRAIGHT"  # 중앙 (직진)
        else:
            # 모멘트 값이 0인 경우 → 라인 없음
            latest_direction = "NO LINE"
    else:
        # 외곽선이 없는 경우 → 라인 없음
        latest_direction = "NO LINE"


# 카메라 처리 루프 (비동기 coroutine)
# → 주기적으로 카메라 프레임 캡처, 라인 분석, 방향 명령 전송, 프레임 WebSocket용 저장
async def camera_loop():
    global latest_frame, last_sent, ser, prev_logical_direction

    # Picamera2 객체 생성
    picam2 = Picamera2()

    # 카메라 설정 구성 (해상도, 포맷 지정)
    config = picam2.create_video_configuration(main={"size": (WIDTH, HEIGHT), "format": "BGR888"})
    picam2.configure(config)

    # 카메라 시작
    picam2.start()
    print("📷 카메라 시작됨")

    # NO LINE 처리 상태 변수 (중복 처리 방지용)
    no_line_handled = False

    # 메인 카메라 처리 루프
    while True:
        start = time.time()

        # 1️⃣ 프레임 캡처
        frame = picam2.capture_array()

        # 2️⃣ 라인 분석 (현재 방향 업데이트됨 → latest_direction 갱신)
        analyze_direction(frame)

        # 3️⃣ 프레임 JPEG 인코딩 후 latest_frame에 저장 (WebSocket용)
        _, jpeg = cv2.imencode(".jpg", frame)
        async with lock:
            latest_frame = jpeg.tobytes()

        # 4️⃣ 자율주행 모드 OFF 상태라면 프레임만 갱신 후 대기
        if not auto_mode:
            await asyncio.sleep(0.03)
            continue

        # 5️⃣ 자율주행 모드 ON 상태면 방향에 따라 시리얼 명령 준비
        direction_code = None

        # 🚗 주행 명령 판단
        if latest_direction == "STRAIGHT":
            send_serial('f')               # 기본 전진(f) 유지
            direction_code = 's'            # STRAIGHT 명령
            prev_logical_direction = "STRAIGHT"
            no_line_handled = False

        elif latest_direction == "LEFT":
            send_serial('f')
            direction_code = 'l'            # 약간 좌회전
            prev_logical_direction = "LEFT"
            no_line_handled = False

        elif latest_direction == "RIGHT":
            send_serial('f')
            direction_code = 'r'            # 약간 우회전
            prev_logical_direction = "RIGHT"
            no_line_handled = False

        elif latest_direction == "LEFT_HARD":
            send_serial('f')
            direction_code = 'L'            # 강하게 좌회전
            prev_logical_direction = "LEFT"
            no_line_handled = False

        elif latest_direction == "RIGHT_HARD":
            send_serial('f')
            direction_code = 'R'            # 강하게 우회전
            prev_logical_direction = "RIGHT"
            no_line_handled = False

        elif latest_direction == "NO LINE":
            # NO LINE 상황 처리 (1회만 처리하도록 no_line_handled 사용)
            if not no_line_handled:
                no_line_handled = True

                # 직전 방향을 기반으로 복귀 동작 실행
                if prev_logical_direction == "LEFT":
                    send_serial('r')  # 우측 복귀 시도
                elif prev_logical_direction == "RIGHT":
                    send_serial('l')  # 좌측 복귀 시도

                send_serial('b')  # 후진(b) 명령

            # NO LINE 처리 후 바로 루프 재진입
            await asyncio.sleep(0.01)
            continue

        # 6️⃣ 중복 명령 방지 (직전과 다른 명령일 때만 시리얼 전송)
        if direction_code and direction_code != last_sent:
            send_serial(direction_code)

        # 7️⃣ 프레임 처리 주기 보정 → 약 100Hz(0.01초) 주기로 루프 유지
        elapsed = time.time() - start
        await asyncio.sleep(max(0, 0.01 - elapsed))

# 시리얼 수신 루프 (비동기 coroutine)
# → 아두이노로부터 수신된 데이터 처리 (자율주행 상태 변경 등)
async def serial_read_loop():
    global ser, auto_mode
    while True:
        # 시리얼 포트가 정상 연결되고 읽을 데이터가 있는 경우
        if ser and ser.in_waiting:
            try:
                # 1바이트 읽기 후 디코딩 및 공백 제거
                data = ser.read().decode('utf-8').strip()

                # 시리얼 로그 기록
                serial_log.append(f"[{time.strftime('%H:%M:%S')}] (recv) {data}")
                print(f"📥 수신됨 ← Arduino: {data}")

                # 수신된 데이터에 따른 상태 처리
                if data == 'a':
                    # 'a' 수신 시 자율주행 모드 ON
                    auto_mode = True
                    send_serial('a')  # 상태 동기화용 'a' 재전송

                elif data == 'n':
                    # 'n' 수신 시 자율주행 모드 OFF
                    auto_mode = False

            except Exception as e:
                # 수신 중 예외 발생 시 에러 출력
                print(f"⚠️ 시리얼 수신 오류: {e}")

        # 주기적으로 대기 (50ms)
        await asyncio.sleep(0.05)

# WebSocket 핸들러 (클라이언트 1명당 개별 코루틴으로 실행됨)
# → 클라이언트에 최신 카메라 프레임 스트리밍 전송
async def handle_client(websocket):
    print(f"📱 클라이언트 접속: {websocket.remote_address}")

    # 접속한 클라이언트를 clients 집합에 등록
    clients.add(websocket)

    try:
        while True:
            async with lock:
                # latest_frame이 존재하면 전송
                if latest_frame is not None:
                    await websocket.send(latest_frame)

            # 약 30fps(1/30초 간격)로 전송 주기 유지
            await asyncio.sleep(1 / 30)

    except Exception as e:
        # WebSocket 오류 발생 시 처리
        print(f"❌ 에러 발생 ({websocket.remote_address}): {e}")

    finally:
        # 클라이언트 연결 종료 시 clients 집합에서 제거
        clients.remove(websocket)
        print(f"🔌 연결 종료: {websocket.remote_address}")

# 메인 실행 함수
# → WebSocket 서버 실행 + 카메라 루프 + 시리얼 수신 루프 병렬 실행
async def main():
    # WebSocket 서버 실행 (0.0.0.0:8765)
    await websockets.serve(handle_client, "0.0.0.0", 8765)
    print("🔌 WebSocket 서버 실행 중 (포트 8765)")

    # camera_loop + serial_read_loop 병렬 실행
    await asyncio.gather(camera_loop(), serial_read_loop())

# 프로그램 진입점
if __name__ == "__main__":
    # HTTP 서버는 별도 스레드에서 실행 (8001포트)
    threading.Thread(target=start_http_server, daemon=True).start()

    # asyncio 기반 메인 coroutine 실행
    asyncio.run(main())