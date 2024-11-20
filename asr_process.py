import logging
import traceback
import numpy as np
import soundfile
import io
import struct
import librosa
import webrtcvad
from multiprocessing import Process
from whisper import WhisperModel
from util import get_today, make_folder

logger = logging.getLogger(__name__)

class ASRProcess(Process):
    """음성 인식 처리를 위한 프로세스 클래스"""
    
    def __init__(self, engine_name, data_queue, args):
        """
        ASR 프로세스 초기화
        
        Parameters
        ----------
        engine_name : str
            엔진 이름
        data_queue : list
            데이터 큐 [입력큐, 출력큐]
        args : dict
            설정 인자
        """
        super().__init__()
        self.args = args
        self.data_in = data_queue[0]
        self.data_out = data_queue[1]
        self.engine_name = engine_name
        self.conf = conf

    def process_audio_segment(self, wavData, epd_start, vad_index, frame_start):
        """
        오디오 세그먼트 처리 및 음성 인식 수행
        
        Parameters
        ----------
        wavData : bytes
            오디오 데이터
        epd_start : int
            음성 검출 시작 지점
        vad_index : int
            VAD 인덱스
        frame_start : float
            프레임 시작 시간
        """
        epd_start_time = (epd_start//FRAME_SIZE) * (FRAME_DURATION_MS/1000)
        epdbuffer = wavData[epd_start:vad_index+FRAME_SIZE+1]
        
        # 오디오 파일 생성 및 리샘플링
        sf = soundfile.SoundFile(
            io.BytesIO(np.array(epdbuffer)), 
            channels=1,
            endian="LITTLE",
            samplerate=SAMPLE_RATE, 
            subtype="PCM_16",
            format="RAW"
        )
        audio, _ = librosa.load(sf, sr=SAMPLE_RATE)
        y_resampled = librosa.resample(audio, orig_sr=SAMPLE_RATE, target_sr=16000)
        
        # Whisper 모델을 통한 음성 인식
        segments, _ = whisper_model.transcribe(
            y_resampled, 
            language="ko", 
            beam_size=5, 
            condition_on_previous_text=False, 
            log_prob_threshold=0.4, 
            vad_filter=True
        )
        
        # 인식 결과 텍스트 생성
        result_text = self.combine_segments(segments)
        
        if result_text:
            resultTxt = f'{epd_start_time:3.1f} {frame_start+(FRAME_DURATION_MS/1000):3.1f} : {result_text}'
            self.data_out.put_nowait(('%R', resultTxt))
            
        return result_text

    def combine_segments(self, segments):
        """
        세그먼트를 결합하여 최종 텍스트 생성
        
        Parameters
        ----------
        segments : list
            인식된 세그먼트 리스트
        """
        result_text = None
        for segment in segments:
            if result_text:
                result_text = f"{result_text} {segment.text}"
            else:
                result_text = segment.text
        return result_text

    def run(self):
        """ASR 프로세스 실행"""
        try:
            logger.info(f'[{self.engine_name}] 프로세스 초기화 성공')
            
            # VAD 초기화
            vad = webrtcvad.Vad()
            vad.set_mode(self.conf["vad_mode"])
            
            # Whisper 모델 초기화
            whisper_model = self.initialize_whisper_model()
            
            while True:
                # 변수 초기화
                wavData = None
                isStart = True
                np_wav = np.zeros(shape=(0), dtype=np.int16)
                vad_index = 0
                epd_start = -1
                triggered = False
                epd_state = 0
                silence_cnt = 0
                
                # 사용자 정보 수신
                (header, buf) = self.data_in.get()
                if header == b'%b':
                    username = buf
                else:
                    continue
                    
                try:
                    while isStart:
                        epdProcessedByteN = 0
                        retResult = None
                        
                        while True:
                            # 데이터 수신
                            (header, buf) = self.data_in.get(timeout=SOCKET_TIMEOUT+1)
                            
                            if header == b'%f':
                                # 종료 패킷 처리
                                self.handle_finish_packet(wavData, triggered)
                                isStart = False
                                break
                                
                            elif header == b'%s':
                                # 음성 데이터 처리
                                wavData = self.process_voice_data(
                                    wavData, buf, epdProcessedByteN, np_wav,
                                    vad_index, vad, triggered, epd_start,
                                    silence_cnt, epd_state
                                )
                                
                            else:
                                # 잘못된 패킷 처리
                                self.handle_illegal_packet(header)
                                isStart = False
                                break

                        # 결과 처리
                        self.process_results(retResult, wavData, epdProcessedByteN)
                        
                        if not isStart:
                            break
                            
                except Exception as e:
                    self.handle_error(e)
                finally:
                    isStart = False
                    
                # 로그 저장
                self.save_log(np_wav, username)
                
                if not isStart:
                    self.data_out.put_nowait(('%F', None))
                    
        except Exception as e:
            self.handle_error(e)

    def initialize_whisper_model(self):
        """Whisper 모델 초기화"""
        if self.conf["device"] == "cpu":
            return WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        elif self.conf["device"] == "cuda":
            return WhisperModel(MODEL_SIZE, device="cuda", compute_type="float32")
        else:
            logger.warn("설정 파일의 device를 확인하세요. 알 수 없는 장치이므로 CPU로 설정됩니다.")
            return WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")

    def handle_error(self, e):
        """에러 처리"""
        error_msg = f'{e.__class__.__name__}:{e}'
        logger.exception(error_msg)
        traceback.print_exc()

    def save_log(self, np_wav, username):
        """로그 저장"""
        today_date, today_time = get_today()
        log_dir = f"{ENGINE_LOG_DIR}/{today_date}"
        make_folder(log_dir)
        filename = f"{today_time}-{username}.pcm"
        np_wav.astype('int16').tofile(f"{log_dir}/{filename}")