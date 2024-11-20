import logging
import threading

class Log:
    """로깅 관리를 위한 클래스"""

    def __init__(self):
        """로거 초기화"""
        self.thread = None

    def get_logger(self, name):
        """
        지정된 이름의 로거 반환
        
        Parameters
        ----------
        name : str
            로거 이름
            
        Returns
        -------
        logging.Logger
            생성된 로거 객체
        """
        return logging.getLogger(name)
    
    def listener_start(self, file_path, level, name, queue):
        """
        로그 리스너 스레드 시작
        
        Parameters
        ----------
        file_path : str
            로그 파일 경로
        level : int
            로깅 레벨
        name : str
            로거 이름
        queue : Queue
            로그 메시지 큐
        """
        self.thread = threading.Thread(
            target=self._proc_log_queue,
            args=(file_path, level, name, queue)
        )
        self.thread.start()

    def listener_end(self, queue):
        """
        로그 리스너 스레드 종료
        
        Parameters
        ----------
        queue : Queue
            종료할 로그 메시지 큐
        """
        queue.put(None)  # 종료 신호 전송
        self.thread.join()  # 스레드 종료 대기

    def _proc_log_queue(self, file_path, level, name, queue):
        """
        로그 큐 처리 메서드
        
        Parameters
        ----------
        file_path : str
            로그 파일 경로
        level : int
            로깅 레벨
        name : str
            로거 이름
        queue : Queue
            처리할 로그 메시지 큐
        """
        self.config_log(file_path, level, name)
        logger = self.get_logger(name)
        
        while True:
            try:
                record = queue.get()
                if record is None:  # 종료 신호 확인
                    break
                logger.handle(record)
            except Exception:
                import sys, traceback
                traceback.print_exc()

    def config_queue_log(self, queue, level, name):
        """
        큐 기반 로거 설정
        
        Parameters
        ----------
        queue : Queue
            로그 메시지 큐
        level : int
            로깅 레벨
        name : str
            로거 이름
            
        Returns
        -------
        logging.Logger
            설정된 로거 객체
        """
        qh = logging.handlers.QueueHandler(queue)
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.addHandler(qh)
        return logger

    def config_log(self, file_path, level, name):
        """
        파일 및 스트림 로거 설정
        
        Parameters
        ----------
        file_path : str
            로그 파일 경로
        level : int
            로깅 레벨
        name : str
            로거 이름
            
        Returns
        -------
        logging.Logger
            설정된 로거 객체
        """
        # 로그 포맷 설정
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] - %(message)s"
        )

        # 스트림 핸들러 설정 (콘솔 출력)
        stream_handler = logging.StreamHandler()
        
        # 파일 핸들러 설정 (자동 로그 로테이션)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            file_path,
            when='midnight',      # 자정마다 로그 파일 교체
            interval=1,           # 1일 간격
            encoding='utf-8',     # UTF-8 인코딩
            backupCount=30        # 최대 30일치 보관
        )

        file_handler.setFormatter(formatter)

        # 로거 설정
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

        return logger