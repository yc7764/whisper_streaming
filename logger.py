import logging
import logging.handlers
from logging import getLogger
from logging.handlers import TimedRotatingFileHandler, QueueHandler
from multiprocessing import Queue
import os
from datetime import datetime

class Log:
    """로깅 관리를 위한 클래스"""

    def __init__(self):
        """로거 초기화"""
        self.logger = None

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
        return getLogger(name)
    
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
        self.logger = self.get_logger(name)
        self.logger.setLevel(level)
        
        # QueueHandler 직접 사용
        qh = QueueHandler(queue)
        self.logger.addHandler(qh)
        
        # 로그 파일 경로 생성
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # TimedRotatingFileHandler 직접 사용
        file_handler = TimedRotatingFileHandler(
            filename=file_path,
            when='midnight',
            interval=1,
            encoding='utf-8'
        )
        
        # 포매터 설정
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def listener_end(self, queue):
        """
        로그 리스너 스레드 종료
        
        Parameters
        ----------
        queue : Queue
            종료할 로그 메시지 큐
        """
        queue.put(None)  # 종료 신호 전송
        self.logger.handlers.clear()  # 로거 핸들러 초기화

    def _proc_log_queue(self, queue):
        """
        로그 큐 처리 프로세스
        
        Parameters
        ----------
        queue : Queue
            처리할 로그 메시지 큐
        """
        while True:
            try:
                record = queue.get()
                if record is None:
                    break
                logger = getLogger(record.name)
                logger.handle(record)
            except Exception as e:
                print(f'Error in log queue processor: {str(e)}')
                break

    def config_queue_log(self, queue, level, name):
        """
        큐 핸들러를 사용하는 로거 설정
        
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
        logger = getLogger(name)
        logger.setLevel(level)
        
        # QueueHandler 직접 사용
        qh = QueueHandler(queue)
        logger.addHandler(qh)
        
        return logger

    def config_log(self, file_path, level, name):
        """
        파일 핸들러를 사용하는 로거 설정
        
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
        logger = getLogger(name)
        logger.setLevel(level)
        
        # 로그 파일 경로 생성
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # TimedRotatingFileHandler 직접 사용
        file_handler = TimedRotatingFileHandler(
            filename=file_path,
            when='midnight',
            interval=1,
            encoding='utf-8'
        )
        
        # 포매터 설정
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        return logger