#!/usr/bin/env python3
# encoding :utf-8

import socket
import configargparse
import struct
import time

def recvall(socket, n):
    """
    소켓으로부터 지정된 바이트 수만큼 데이터를 수신
    
    Parameters
    ----------
    socket : socket
        통신용 소켓
    n : int
        수신할 바이트 수
    """
    sock = socket
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    
    if(n > len(data)):
        data[n] = b'\x00'
    return data

def recv_packet(client_socket):
    """
    서버로부터 패킷을 수신하고 헤더 코드, 길이, 데이터를 반환
    
    Parameters
    ----------
    client_socket : socket
        클라이언트 소켓
    """
    # 헤더 코드 수신 (2바이트)
    hCode, = struct.unpack('>2s', bytes(recvall(client_socket, 2)))
    
    # 최종 결과인 경우
    if hCode == b'%F':
        return hCode, 0, None
    
    # 데이터 길이 수신 (4바이트)
    hLen, = struct.unpack('>4s', bytes(recvall(client_socket, 4)))
    hLen = int(hLen, 16)
    
    # 데이터 수신
    if hLen > 0: 
        data = recvall(client_socket, hLen)
    else: 
        data = None
        
    return hCode, hLen, data

def get_parser():
    """설정 파서 생성"""
    parser = configargparse.ArgumentParser(
        description='Whisper Streaming 클라이언트',
        config_file_parser_class=configargparse.YAMLConfigFileParser,
        formatter_class=configargparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument('--ip', type=str, default="localhost",
                       help='서버 IP 주소', required=True)
    parser.add_argument('--port', type=str, default='5000',
                       help='서버 포트')
    parser.add_argument('--ifn', required=True, 
                       help='입력 PCM 파일 경로')
                       
    return parser

if __name__ == '__main__':
    # 설정 파싱
    parser = get_parser()
    args = parser.parse_args()
    FILE_PATH = args.ifn

    # 1. WAV 파일 읽기
    wavData = []
    with open(FILE_PATH, 'rb') as f:
        while True:
            wavByteData = f.read(3200)
            if len(wavByteData) <= 0:
                break
            else:
                wavData.append(wavByteData)
    print(f"청크 개수: {len(wavData)}")

    # 2. 서버 연결 및 매직 스트링 전송
    sock = socket.socket()
    host = args.ip
    port = int(args.port)
    sock.connect((host, port))
    MAGIC_STRING = b'WHISPER_STREAMING_V1.0'
    sock.sendall(MAGIC_STRING)
    hCode, hLen, data = recv_packet(sock)
    print(hCode, hLen, data)

    # 3. 사용자 ID 전송 및 환영 메시지 수신
    sock.sendall(b'%u0006yc7764')
    hCode, hLen, data = recv_packet(sock)
    print(hCode, hLen, data)
    sock.sendall(b'%b0000')

    # 4. 음성 데이터 전송
    for chunk in wavData:
        chunk_size = format(len(chunk), '04x')
        block = bytearray(b'%s')
        block += chunk_size.encode()
        block += chunk
        sock.sendall(block)  # 헤더, 크기, 청크 전송
    sock.sendall(b'%f0000')  # 마지막 블록 전송

    # 5. 결과 수신
    result = ''
    while True:
        hCode, hLen, data = recv_packet(sock)
        if data is not None:
            data = data.decode('utf-8')
        if hCode == b'%E':  # EPD 코드
            continue
        if hCode == b'%R':  # 인식 결과
            print(hCode, hLen, data)
            temp = data.split(':')
            result += temp[1].strip() + " "
        if hCode == b'%F':  # 최종 결과
            break
    print(result)