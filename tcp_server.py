import logging
import traceback
import socket
import threading
import signal
import os
from time import sleep
from queue import Queue
from asr_process import asr_process
from util import *
import struct

logger = logging.getLogger(__name__)

MAGIC_STRING = b'WHISPER_STREAMING_V1.0'
ENGINE_LIST = []

def recv_magicstring(client_socket):
    ret_magicstring = struct.unpack('>22s',bytes(recvall(client_socket,22)))
    print(ret_magicstring[0],"!")
    if ret_magicstring[0] == MAGIC_STRING: 
        return True
    else:
        return False
    
def recv_packet(client_socket):
    hCode,hLen = struct.unpack('>2s4s', bytes(recvall(client_socket, 6)))
    hLen=int(hLen,16)
    if hLen>0: 
        data=recvall(client_socket,hLen)
    else: 
        data=None

    return hCode,hLen,data

def handle_client(client_socket,ip,addr):
    client_socket.settimeout(SOCKET_TIMEOUT)
## stage 0: check magic string
    if MAGIC_STRING is not None:
        ret=recv_magicstring(client_socket)
        if ret == False:
            illegal_packet_error_log(client_socket,ip, addr, 'INVALID_MAGICSTRING')
            return

    try:
        pCode, pLen, pData = recv_packet(client_socket)
    except socket.timeout:
        timeout_error_log(client_socket,ip, addr, 'TIME_OUT')
        error_msg = f'IP[{ip}] : TIME_OUT_USERNAME'
        logger.error(error_msg)
        return
    except Exception as e:
        illegal_packet_error_log(client_socket,ip, addr, 'ILLEGAL_PACKET_USERNAME')
        return
    
    if pCode == b'%u':
        username=pData.decode('utf-8')
    elif pCode == b'%c':
        for idx,engine in enumerate(ENGINE_LIST):
            if engine['running']:
                msg = 'engine ' + str(idx) + ': running'
                client_socket.sendall(bytes('%%C%04x%s' % (len(msg), msg), encoding='utf-8'))
            else:
                msg = 'engine ' + str(idx) + ': sleeping'
                client_socket.sendall(bytes('%%C%04x%s' % (len(msg), msg), encoding='utf-8'))
        client_socket.sendall(b'%F0000')
        client_socket.close()
        return
    else:
        illegal_packet_error_log(client_socket,ip, addr, 'ILLEGAL_PACKET_USERNAME')
        return
        
## stage 2: initialize engine information from client
    allocated = False
    eid = -1
    
## stage 3: get idle engine & set engine to busy
    for i in range(ENGINE_TIMEOUT):
        for idx,engine in enumerate(ENGINE_LIST):
            if engine['running']:
                continue
            else:
                engine['running']=True
                eid=idx
                asr_process=engine['process']
                allocated=True
                logger.info(f'USER[{username}] : Engine[{asr_process.engine_name}] : running')
                break
        if allocated:
            break
        else:
            sleep(1)

## stage 4: receive signal buffer & send recognition result
    if allocated:
        msg='welcome message for user[%s]'%username
        logger.info(f'IP[{ip}] : {msg}')
        try:
            client_socket.sendall(bytes('%%L%04x%s' % (len(msg), msg), encoding='utf-8'))

            while(True):
                pCode, pLen, pData = recv_packet(client_socket)
                logger.info(f'USER[{username}] : recv packet code[{pCode}] len[{pLen}]]')
                if pCode == b'%b': 
                    break
                else:
                    illegal_packet_error_log(client_socket,ip, addr, 'ILLEGAL_PACKET')
                    return
        except Exception as e:
            illegal_packet_error_log(client_socket,ip, addr, 'DISCONNECTED_WELCOME_MSG')
            return
        except socket.timeout:
            timeout_error_log(client_socket,ip, addr, 'TIME_OUT')
            error_msg = f'IP[{ip}] - Userid[{username}] : TIME_OUT_BEGIN_MSG'
            logger.error(error_msg)
            return

        logger.info(f'[{asr_process.engine_name}] is allocated from {ip}')
        session=True

        ## clear queue ####
        try:
            while not asr_process.data_out.empty():
                asr_process.data_out.get_nowait()
            while not asr_process.data_in.empty():
                asr_process.data_in.get_nowait()
        except Exception as e:
            error_msg = f'USER[{username}] - Engine[{asr_process.engine_name}] : {e.__class__.__name__}:{e}'
            logger.exception(error_msg)

        def read_asr_process(socket):
            while (True):
                sleep(0.001)
                try:
                    (pCode, pData) = asr_process.data_out.get()
                    logger.info(f"USER[{username}] : Engine[{asr_process.engine_name}] : "
                         f"Response Packet :: code[{pCode}] :: data[{pData}]")
                    
                    if pCode == '%F':
                        client_socket.sendall(b'%F0000')
                        client_socket.close()
                        break
                    elif pCode == '%R':
                        msg = bytes(pData,encoding='utf-8')
                        msg_len = len(msg)
                        cmd = bytes('%R',encoding='utf-8')
                        client_socket.sendall(cmd+bytes('%04x'%msg_len,encoding='utf-8')+msg)
                    elif pCode == '%E':
                        msg = bytes(pData, encoding='utf-8')
                        msg_len = len(msg)
                        cmd = bytes('%E', encoding='utf-8')
                        client_socket.sendall(cmd + bytes('%04x' % msg_len, encoding='utf-8') + msg)
                    else:   
                        logger.error(f"UNKNOWN_PCODE:{pCode}-{pData}")
                        pass
                except Exception as e:
                    error_msg = f'USER[{username}] - Engine[{asr_process.engine_name}] : {e.__class__.__name__}:{e}'
                    logger.exception(error_msg)
                    break
        try:
            pCode, pLen, pData = recv_packet(client_socket)
            logger.info(f'[{asr_process.engine_name}]-USER[{username}] : recv code[{pCode}] len[{pLen}]')
            if pCode == b'%f':
                client_socket.sendall(b'%F0000')
                logger.info(f"USER[{username}] : Engine[{asr_process.engine_name}] : "
                         f"Response Packet :: code[{pCode}] :: data[{pData}]")
                client_socket.close()
                sleep(1)
                ENGINE_LIST[eid]['running']=False;
            else:
                t1=threading.Thread(target=read_asr_process,args=(client_socket,))
                t1.start()

                asr_process.data_in.put((b'%b', username))
                asr_process.data_in.put((pCode,pData))

                while session:
                    pCode, pLen, pData = recv_packet(client_socket)
                    logger.info(f'[{asr_process.engine_name}]-USER[{username}] : recv code[{pCode}] len[{pLen}]')
                    asr_process.data_in.put((pCode,pData))

                    if pCode == b'%f':
                        break
                t1.join()
        except socket.timeout:
            error_msg = f'[{asr_process.engine_name}]-USER[{username}] : time_out error'
            logger.error(error_msg)
            timeout_error_log(client_socket,ip, addr, 'TIME_OUT')
            logger.info(f"USER[{username}] : Engine[{asr_process.engine_name}] : "
                         f"Response Packet :: code[%%F] :: data[TIME_OUT]")
        except Exception as e:
            error_msg = f'USER[{username}] - Engine[{asr_process.engine_name}] : {e.__class__.__name__}:{e}'
            logger.exception(error_msg)
        finally:
            try:
                while not asr_process.data_out.empty():
                    asr_process.data_out.get_nowait()
                while not asr_process.data_in.empty():
                    asr_process.data_in.get_nowait()
                asr_process.data_in.put((b'%f', None))
            except Exception as e:
                error_msg = f'USER[{username}] - Engine[{asr_process.engine_name}] : {e.__class__.__name__}:{e}'
                logger.exception(error_msg)

            sleep(1)
            ENGINE_LIST[eid]['running']=False;
            
            logger.info(f"USER[{username}] : Engine[{asr_process.engine_name}] : "
                 f"read_asr_process_done")
    
    else:
        msg = '{"reason": "SERVER_TOO_BUSY"}'
        logger.error(f'SERVER_TOO_BUSY :: USER[{username}]')
        try:
            client_socket.sendall(bytes('%%R%04x%s'%(len(msg),msg),encoding='utf-8'))
            client_socket.sendall(b'%F0000')
            client_socket.close()
        except Exception as e:
            error_msg = f'{e.__class__.__name__}:{e}'
            logger.exception(error_msg)
            traceback.print_exc()
def main(args):
    main_parser = get_parser()

    global MAX_CLIENT_N
    global childs,ip
    
    arguments = ['--lan', 'ko', '--task', 'transcribe',
    '--model_dir', conf['language']]
    g_args = main_parser.parse_args(arguments)

    global logger
    listeners = Log()
    listeners.listener_start(LOGFILENAME, level, 'listener', log_queue)
    logger = Log().config_queue_log(log_queue, level, 'log')

    for i in range(conf['channel']):
        g_args.model = conf['model']
        import copy
        args=copy.deepcopy(g_args)
        ENGINE_NAME=conf['language']+":"+str(i)
        ENGINE_LIST.append({'running':False,'process':asr_process(ENGINE_NAME,(Queue(),Queue()),args)})

    for engine in ENGINE_LIST:
        engine['process'].start()
    logger.info(f'Starting up listener on localhost:{g_args.port} with mappings')
    
    global server_socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((ip,g_args.port))
    server_socket.listen(MAX_CLIENT_N)
    while True:
        try:
            client_socket,(ip,addr) = server_socket.accept()
        except Exception as ex:
            error_msg = f'{ex.__class__.__name__}:{ex}'
            logger.exception(error_msg)
            break;
        t= threading.Thread(target=handle_client,args=(client_socket,ip,addr))
        t.daemon=True
        t.start()
    listeners.listener_end(log_queue)
    signal.signal(signal.SIGINT, signal_handler)
    os.wait()

if __name__ == '__main__':
    main(sys.argv[1:])
