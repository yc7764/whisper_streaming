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
from datetime import datetime

from util import get_today, make_folder

logger = logging.getLogger(__name__)

class ASRConfig:
    """ASR 설정을 관리하는 클래스"""
    def __init__(self, **kwargs):
        # 오디오 설정
        self.frame_size = kwargs.get('frame_size', 480)  # 16000Hz * 30ms = 480
        self.sample_rate = kwargs.get('sample_rate', 16000)
        self.frame_duration_ms = kwargs.get('frame_duration_ms', 30)
        
        # VAD 설정
        self.vad_mode = kwargs.get('vad_mode', 1)
        
        # 네트워크 설정
        self.socket_timeout = kwargs.get('socket_timeout', 60)
        
        # 모델 설정
        self.model_size = kwargs.get('model_size', 'base')
        self.device = kwargs.get('device', 'cpu')
        self.language = kwargs.get('language', 'ko')
        
        # 로깅 설정 추가
        self.save_pcm = kwargs.get('save_pcm', False)
        self.pcm_path = kwargs.get('pcm_path', 'pcm_files')

class ASRProcess(Process):
    """실시간 음성 인식을 처리하는 프로세스 클래스"""

    def __init__(self, engine_name, data_queue, config=None):
        """
        ASR 프로세스 초기화
        
        Parameters
        ----------
        engine_name : str
            엔진 이름
        data_queue : list
            데이터 큐 [입력큐, 출력큐]
        config : ASRConfig, optional
            ASR 설정 객체. None인 경우 기본값 사용
        """
        super().__init__()
        self.data_in = data_queue[0]
        self.data_out = data_queue[1]
        self.engine_name = engine_name
        self.config = config or ASRConfig()

    def process_audio_segment(self, wavData, epd_start, vad_index, frame_start, whisper_model):
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
        whisper_model : WhisperModel
            Whisper 모델 인스턴스
        """
        epd_start_time = (epd_start//self.config.frame_size) * (self.config.frame_duration_ms/1000)
        epdbuffer = wavData[epd_start:vad_index+self.config.frame_size+1]
        
        # 오디오 파일 생성 및 리샘플링
        sf = soundfile.SoundFile(
            io.BytesIO(np.array(epdbuffer)), 
            channels=1,
            endian="LITTLE",
            samplerate=self.config.sample_rate, 
            subtype="PCM_16",
            format="RAW"
        )
        audio, _ = librosa.load(sf, sr=self.config.sample_rate)
        y_resampled = librosa.resample(audio, orig_sr=self.config.sample_rate, target_sr=16000)
        
        # Whisper 모델을 통한 음성 인식
        segments, _ = whisper_model.transcribe(
            y_resampled, 
            language=self.config.language, 
            beam_size=5, 
            condition_on_previous_text=False,
            log_prob_threshold=0.4, 
            vad_filter=True
        )
        
        # 인식 결과 텍스트 생성
        result_text = self.combine_segments(segments)
        
        if result_text:
            resultTxt = f'{epd_start_time:3.1f} {frame_start+(self.config.frame_duration_ms/1000):3.1f} : {result_text}'
            self.data_out.put_nowait(('%R', resultTxt))
            
        return result_text
    def process_voice_data(self, wavData, buf, np_wav, vad_index, 
                          vad, triggered, epd_start, silence_cnt, epd_state, whisper_model):
        """음성 데이터 처리 및 VAD 적용"""
        # 새로운 데이터 추가
        if wavData is None:
            wavData = buf
        else:
            wavData.extend(buf)
        
        # 바이트 데이터를 short 타입으로 변환
        epdShortBuffer = struct.unpack('h' * (len(buf) // 2), buf)
        np_wav = np.concatenate((np_wav, np.array(epdShortBuffer, dtype=np.int16)), axis=0)
        
        # VAD 처리
        while vad_index + self.config.frame_size <= len(wavData):
            frame = wavData[vad_index:vad_index+self.config.frame_size]
            frame_start = (vad_index//self.config.frame_size) * (self.config.frame_duration_ms/1000)
            
            if vad.is_speech(frame, self.config.sample_rate):
                if not triggered:
                    # 음성 구간 시작
                    triggered = True
                    epd_state = 1
                    epd_start = vad_index
                    silence_cnt = 0
                else:
                    epd_state = 1
                    if frame_start+(self.config.frame_duration_ms/1000) - (epd_start//self.config.frame_size)*(self.config.frame_duration_ms/1000) > 10:
                        # 음성 구간이 너무 길 경우 중간 처리
                        self.process_audio_segment(wavData, epd_start, vad_index, frame_start, whisper_model)
                        triggered = False
            else:
                silence_cnt += 1
                if triggered:
                    if silence_cnt > 16:
                        # 무음 구간이 충분히 길어 음성 구간 종료로 판단
                        epd_state = 2
                        triggered = False
                        self.process_audio_segment(wavData, epd_start, vad_index, frame_start, whisper_model)
                    else:
                        epd_state = 1
                else:
                    epd_state = 0
            
            vad_index += self.config.frame_size
        
        return wavData, triggered, epd_start, silence_cnt, epd_state, vad_index

    def handle_finish_packet(self, np_wav, triggered, epd_start, whisper_model):
        """종료 패킷 처리"""
        if triggered:
            frame_start = (len(np_wav)//self.config.frame_size) * (self.config.frame_duration_ms/1000)
            self.process_audio_segment(np_wav, epd_start, len(np_wav), frame_start, whisper_model)
            logger.info(f'Engine[{self.engine_name}] : 인식 종료')

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

    def handle_illegal_packet(self, header):
        """잘못된 패킷 처리"""
        self.data_out.put_nowait(('%F', None))
        error_msg = f'Engine[{self.engine_name}] : ILLEGAL_PACKET : header[{header}]'
        logger.error(error_msg)
        
    def initialize_whisper_model(self):
        """Whisper 모델 초기화"""
        return WhisperModel(
            model_size=self.config.model_size,
            device=self.config.device,
            compute_type="float16"
        )

    def save_log(self, np_wav, username):
        """
        음성 데이터와 로그를 저장
        
        Parameters
        ----------
        np_wav : numpy.ndarray
            저장할 음성 데이터 배열
        username : str
            사용자 이름
        """
        try:
            # 현재 날짜와 시간으로 파일명 생성
            current_date, current_time = get_today()
            
            # PCM 파일 저장 (옵션)
            if hasattr(self.config, 'save_pcm') and self.config.save_pcm:
                pcm_dir = self.config.pcm_path or "pcm_files"
                make_folder(pcm_dir)
                
                pcm_filename = f"{pcm_dir}/{current_date}_{username}_{current_time}.pcm"
                with open(pcm_filename, 'wb') as f:
                    f.write(np_wav.tobytes())
                
                logger.info(f"Engine[{self.engine_name}] : PCM 파일 저장 완료 - {pcm_filename}")
                
        except Exception as e:
            error_msg = f"Engine[{self.engine_name}] : 로그 저장 실패 - {str(e)}"
            logger.error(error_msg)
            logger.exception(e)

    def handle_error(self, e):
        """
        예외 처리 및 로깅
        
        Parameters
        ----------
        e : Exception
            처리할 예외 객체
        """
        error_msg = f"Engine[{self.engine_name}] : {e.__class__.__name__}:{str(e)}"
        logger.error(error_msg)
        logger.exception(e)
        self.data_out.put_nowait(('%E', error_msg))

    def run(self):
        """ASR 프로세스 실행"""
        try:
            logger.info(f'[{self.engine_name}] 프로세스 초기화 성공')
            
            # VAD 초기화
            vad = webrtcvad.Vad()
            vad.set_mode(self.config.vad_mode)
            
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
                if header != b'%b':
                    continue
                username = buf
                
                try:
                    epdProcessedByteN = 0
                    retResult = None

                    while isStart:
                        # 데이터 수신
                        (header, buf) = self.data_in.get(timeout=self.config.socket_timeout+1)
                        
                        if header == b'%f':
                            # 종료 패킷
                            self.handle_finish_packet(np_wav, triggered, epd_start, whisper_model)
                            isStart = False
                            
                        elif header == b'%s':
                            # 음성 데이터 처리
                            wavData, triggered, epd_start, silence_cnt, epd_state, vad_index = \
                                self.process_voice_data(wavData, buf, np_wav,
                                                        vad_index, vad, triggered, epd_start,
                                                        silence_cnt, epd_state, whisper_model)
                        else:
                            # 잘못된 패킷 처리
                            self.handle_illegal_packet(header)
                            isStart = False
                            
                except Exception as e:
                    self.handle_error(e)
                finally:
                    logger.info(f'Engine[{self.engine_name}] : {username} 요청 처리 종료')
                    self.data_out.put_nowait(('%F', None))
                    # 로그 저장
                    self.save_log(np_wav, username)
                    
        except Exception as e:
            self.handle_error(e)