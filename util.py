import datetime
import os
import signal
import sys
import logging

logger = logging.getLogger(__name__)

def get_today():
    """
    현재 날짜와 시간을 반환
    
    Returns
    -------
    tuple
        (날짜(YYYY-MM-DD), 시간(HH-MM-SS-ms))
    """
    now = datetime.datetime.now()
    return now.strftime('%Y-%m-%d'), now.strftime('%H-%M-%S-%f')

def make_folder(folder_name):
    """
    폴더가 존재하지 않을 경우 새로 생성
    
    Parameters
    ----------
    folder_name : str
        생성할 폴더 경로
    """
    if not os.path.isdir(folder_name):
        os.mkdir(folder_name)

def signal_handler(sig, frame):
    """
    Ctrl+C 시그널 처리 핸들러
    프로세스와 리스너를 안전하게 종료
    
    Parameters
    ----------
    sig : signal
        수신된 시그널
    frame : frame
        현재 스택 프레임
    """
    global childs, listeners
    print('Ctrl+C가 입력되었습니다!')
    
    # 모든 자식 프로세스 종료
    for child in childs:
        os.kill(child, signal.SIGKILL)
    
    # 모든 리스너 종료    
    for listener in listeners:
        os.kill(listener.pid, signal.SIGTERM)
    
    # 현재 프로세스 종료
    os.kill(os.getpid(), signal.SIGKILL)
    sys.exit(0)

def illegal_packet_error_log(client_socket, ip, addr, log_msg):
    """
    잘못된 패킷 수신 시 에러 처리 및 로깅
    
    Parameters
    ----------
    client_socket : socket
        클라이언트 소켓
    ip : str
        클라이언트 IP 주소
    addr : tuple
        클라이언트 주소 정보
    log_msg : str
        로깅할 에러 메시지
    """
    try:
        # 종료 신호 전송 후 소켓 닫기
        client_socket.sendall(b'%F0000')
        client_socket.close()
    except Exception as e:
        pass
    
    # 에러 로깅
    error_msg = f'IP[{ip}] : {log_msg}'
    logger.error(error_msg)

def timeout_error_log(client_socket, ip, addr, log_msg):
    """
    타임아웃 발생 시 에러 처리 및 로깅
    
    Parameters
    ----------
    client_socket : socket
        클라이언트 소켓
    ip : str
        클라이언트 IP 주소
    addr : tuple
        클라이언트 주소 정보
    log_msg : str
        로깅할 에러 메시지
    """
    try:
        # 에러 메시지 포함하여 종료 신호 전송 후 소켓 닫기
        error_packet = bytes('%%F%04x%s' % (len(log_msg), log_msg), encoding='utf-8')
        client_socket.sendall(error_packet)
        client_socket.close()
    except Exception as e:
        pass