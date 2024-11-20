def get_parser():
    """
    Whisper 스트리밍을 위한 명령행 인자 파서 생성
    
    Returns
    -------
    ArgumentParser
        설정된 인자 파서 객체
    """
    parser = argparse.ArgumentParser(description='Whisper 스트리밍 설정')
    
    # 오디오 청크 크기 설정
    parser.add_argument(
        '--min-chunk-size', 
        type=float, 
        default=1.0, 
        help='최소 오디오 청크 크기(초). 처리를 위해 이 시간만큼 대기합니다. '
             '처리 시간이 이보다 짧으면 대기하고, 길면 수신된 전체 세그먼트를 처리합니다.'
    )
    
    # Whisper 모델 설정
    parser.add_argument(
        '--model', 
        type=str, 
        default='large-v2',
        choices="tiny.en,tiny,base.en,base,small.en,small,medium.en,medium,large-v1,large-v2,large".split(","),
        help='사용할 Whisper 모델 크기 (기본값: large-v2). '
             '모델이 캐시 디렉토리에 없으면 자동으로 다운로드됩니다.'
    )
    
    # 모델 디렉토리 설정
    parser.add_argument(
        '--model_dir', 
        type=str, 
        default=None, 
        help='Whisper model.bin 및 관련 파일이 저장된 디렉토리. '
             '--model과 --model_cache_dir 매개변수를 재정의합니다.'
    )
    
    # 언어 설정
    parser.add_argument(
        '--lan', '--language', 
        type=str, 
        default='en', 
        help='전사를 위한 언어 코드 (예: en,de,cs)'
    )
    
    # 작업 유형 설정
    parser.add_argument(
        '--task', 
        type=str, 
        default='transcribe',
        choices=["transcribe", "translate"],
        help='작업 유형: 전사(transcribe) 또는 번역(translate)'
    )
    
    # 시작 시간 설정
    parser.add_argument(
        '--start_at', 
        type=float, 
        default=0.0, 
        help='오디오 처리 시작 시간'
    )
    
    # 백엔드 설정
    parser.add_argument(
        '--backend', 
        type=str, 
        default="faster-whisper",
        choices=["faster-whisper", "whisper_timestamped"],
        help='Whisper 처리를 위한 백엔드 선택'
    )
    
    # 오프라인 모드 설정
    parser.add_argument(
        '--offline', 
        action="store_true", 
        default=False, 
        help='오프라인 모드 활성화'
    )
    
    # 계산 인식 시뮬레이션 설정
    parser.add_argument(
        '--comp_unaware', 
        action="store_true", 
        default=False, 
        help='계산 인식 없는 시뮬레이션 모드'
    )
    
    # VAD 설정
    parser.add_argument(
        '--vad', 
        action="store_true", 
        default=False, 
        help='음성 활성 감지(VAD) 기본 매개변수 사용'
    )
    
    # 포트 설정
    parser.add_argument(
        '--port', 
        type=int, 
        default=PORT,
        help='서버 포트 번호'
    )
    
    return parser