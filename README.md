# Whisper Streaming STT Server

실시간 음성 인식을 위한 Whisper 기반 스트리밍 STT(Speech-to-Text) 서버입니다.

## 주요 기능

- 실시간 음성 스트리밍 처리
- WebRTC VAD를 통한 음성 구간 감지
- Whisper 모델을 이용한 고성능 음성 인식
- 멀티 채널 동시 처리 지원
- PCM 음성 데이터 저장 기능 (선택적)

## 시스템 요구사항

- Python 3.8 이상
- CUDA 지원 GPU (선택적)
- Anaconda/Miniconda (권장)

## 설치 방법

1. 환경 설정
```bash
# Anaconda 환경 생성
conda create -n whisper_streaming python=3.8
conda activate whisper_streaming

# 필요한 패키지 설치
pip install -r requirements.txt
```

2. 설정 파일 수정
`config_vad.yaml` 파일에서 서버 설정을 조정할 수 있습니다:
```yaml
# 오디오 설정
audio:
  frame_size: 480        # 16000Hz * 30ms = 480
  sample_rate: 16000     # 샘플링 레이트
  frame_duration_ms: 30  # 프레임 길이

# 서버 설정
network:
  socket_timeout: 60     # 소켓 타임아웃 (초)
  ip: "127.0.0.1"       # 서버 IP
  port: 5000            # 서버 포트

# Whisper 모델 설정
model:
  size: "base"          # 모델 크기 (tiny/base/small/medium/large-v2)
  device: "cuda"        # 실행 장치 (cpu/cuda)
  language: "ko"        # 인식 언어
  channel: 1            # 동시 처리 채널 수
```

## 실행 방법

1. 서버 실행
```bash
python tcp_server.py
```

2. 클라이언트 실행 (테스트용)
```bash
python tcp_client.py --ip localhost --port 5000 --ifn test.pcm
```

## 프로젝트 구조

```
whisper_streaming/
├── asr_process.py      # ASR 프로세스 구현
├── tcp_server.py       # TCP 서버 구현
├── tcp_client.py       # TCP 클라이언트 (테스트용)
├── config_vad.yaml     # 설정 파일
├── logger.py           # 로깅 유틸리티
├── util.py             # 유틸리티 함수
└── requirements.txt    # 패키지 의존성 목록
```

## 주요 클래스 설명

### ASRProcess
- 실시간 음성 인식을 처리하는 프로세스 클래스
- VAD를 통한 음성 구간 감지
- Whisper 모델을 이용한 음성 인식 수행

### ASRConfig
- ASR 관련 설정을 관리하는 클래스
- 오디오, VAD, 네트워크, 모델 설정 포함

## 프로토콜 설명

### 연결 초기화
1. 매직 스트링 확인
   - 클라이언트는 연결 직후 매직 스트링을 전송
   - 매직 스트링: `WHISPER_STREAMING_V1.0`
   - 서버는 매직 스트링을 검증하여 올바른 클라이언트인지 확인

### 패킷 구조

1. 기본 패킷 구조
```
+----------------+------------------+------------------+
|  Header Code   |  Data Length    |     Data        |
|    (2 bytes)   |    (4 bytes)    |  (variable)     |
+----------------+------------------+------------------+
```

2. 상세 설명
- Header Code
  - 2바이트 문자열 (예: %u, %s, %R 등)
  - % 문자로 시작
  - 패킷의 용도를 나타냄

- Data Length
  - 4바이트 16진수 문자열
  - 데이터 영역의 길이를 나타냄
  - 범위: 0000-FFFF
  - 예: "0000" (데이터 없음), "000A" (10바이트)

- Data
  - 가변 길이 데이터
  - 문자열 또는 바이너리 데이터
  - Length에 명시된 길이만큼의 데이터

3. 패킷 예시
```
1) 사용자 ID 전송
[Header] %u
[Length] 0008
[Data  ] user1234

2) 음성 데이터 전송
[Header] %s
[Length] 0960
[Data  ] <PCM binary data...>

3) 인식 결과 수신
[Header] %R
[Length] 0015
[Data  ] 1.2 3.4 : 안녕하세요

4) 에러 메시지
[Header] %E
[Length] 0014
[Data  ] Invalid packet
```

### 통신 패킷 명세
#### 클라이언트 -> 서버 패킷

| 헤더 | 설명 | 데이터 형식 | 예시 |
|------|------|------------|------|
| `%u` | 사용자 ID 전송 | ASCII 문자열 | `%u0008user1234` |
| `%b` | 음성 인식 시작 | 데이터 없음 | `%b0000` |
| `%s` | 음성 데이터 | PCM 바이너리<br>(16kHz, 16bit, mono) | `%s0960[PCM DATA]` |
| `%f` | 음성 인식 종료 | 데이터 없음 | `%f0000` |
| `%c` | 서버 상태 확인 | 데이터 없음 | `%c0000` |

#### 서버 -> 클라이언트 패킷

| 헤더 | 설명 | 데이터 형식 | 예시 |
|------|------|------------|------|
| `%L` | 환영 메시지 | ASCII 문자열 | `%L001AWelcome!` |
| `%R` | 인식 결과 | `[시작시간 종료시간 : 텍스트]` | `%R0015"1.2 3.4 : 안녕하세요"` |
| `%E` | 에러 메시지 | ASCII 문자열 | `%E0014"Invalid packet"` |
| `%F` | 종료 신호 | 데이터 없음 | `%F0000` |
| `%C` | 서버 상태 응답 | ASCII 문자열 | `%C0012"engine 0: running"` |

### 패킷 데이터 형식

1. PCM 음성 데이터
   - sampling rate: 16kHz
   - bit rate: 16bit signed integer
   - channel: mono
   - frame 크기: 480 samples (30ms)
   - endian: Little-endian

2. 텍스트 데이터
   - 인코딩: UTF-8
   - encoding: Unicode
   - 최대 길이: 65535 bytes (0xFFFF)

3. 시간 정보
   - 단위: 초
   - 소수점: 첫째 자리까지 (0.1초 단위)
   - 형식: "시작시간 종료시간"

### 통신 흐름

```
[연결 초기화]
Client                                      Server
  |                                           |
  |  1. WHISPER_STREAMING_V1.0                |
  |-----------------------------------------> |
  |                                           |
  |  2. 사용자 ID (%u)                         |
  |-----------------------------------------> |
  |                                           |
  |  3. 환영 메시지 (%L)                       |
  |<----------------------------------------- |
  |                                           |
  |  4. 시작 신호 (%b)                         |
  |-----------------------------------------> |
  |                                           |

[음성 인식 처리]
  |                                           |
  |  5. 음성 데이터 전송 (%s)                  |
  |-----------------------------------------> |
  |                                           |
  |         [VAD 처리]                        |
  |         - 음성 구간 감지                   |
  |         - 무음 구간 감지                   |
  |                                           |
  |  6. 인식 결과 수신 (%R)                    |
  |<----------------------------------------- |
  |    (VAD 결과에 따라 선택적으로 전송)        |
  |                                           |
  |            5-6 반복                       |
  |                                           |

[연결 종료]
  |                                           |
  |  7. 종료 요청 (%f)                         |
  |-----------------------------------------> |
  |                                           |
  |  8. 종료 확인 (%F)                         |
  |<----------------------------------------- |
  |                                           |
```

### VAD(Voice Activity Detection) 처리

1. 음성 데이터 수신 시
   - 서버는 수신된 음성 데이터를 WebRTC VAD로 분석
   - 프레임 단위(30ms)로 음성/무음 판단

2. 음성 구간 감지 시
   - triggered = true로 설정
   - 음성 데이터 누적 시작
   - 음성 구간이 10초 이상 지속되면 강제로 인식 처리

3. 무음 구간 감지 시
   - 이전 상태가 음성 구간(triggered = true)인 경우
     - 16프레임(480ms) 이상 무음이 지속되면 음성 구간 종료로 판단
     - 누적된 음성 데이터에 대해 Whisper 모델로 인식 수행
     - 인식 결과가 있는 경우에만 클라이언트에 전송
   - 이전 상태가 무음 구간인 경우
     - 데이터 무시

4. 주요 파라미터
   - frame_duration_ms: 30ms (프레임 길이)
   - sample_rate: 16000Hz (샘플링 레이트)
   - vad_mode: 1 (VAD 감도, 0-3)
   - silence_threshold: 16 frames (무음 판단 임계값)
   - max_speech_duration: 10 seconds (최대 음성 구간)

### 에러 처리
- 잘못된 매직 스트링: 즉시 연결 종료
- 타임아웃 발생: 60초 무응답 시 연결 종료
- 패킷 오류: 에러 메시지 전송 후 연결 종료
- 서버 과부하: "SERVER_TOO_BUSY" 메시지 전송 후 연결 종료

## 주의사항

1. CUDA 사용 시 적절한 CUDA 버전 설치 필요
2. 충분한 시스템 메모리 확보 필요
3. 네트워크 설정 시 방화벽 고려
4. 동시 접속자 수 제한 확인
