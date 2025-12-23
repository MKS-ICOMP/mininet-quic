# udp_client_final.py
#
# Cliente "QUIC-sim" baseado em UDP:
# - Envia handshake
# - Envia pacotes "data"
# - [NOVO] Envia arquivo quebrado em chunks (base64)
# - Retransmite em caso de timeout

import socket
import json
import time
import base64
import os

# Ajustar este IP para o IP do servidor visto de dentro do Mininet.
SERVER_IP = "10.0.0.1"
SERVER_PORT = 4433

TIMEOUT = 5.0       # timeout para esperar ACK
MAX_RETRIES = 10    # retransmissões por pacote
NUM_DATA_PKTS = 5   # quantos pacotes de dados simples enviar

# Configurações do arquivo (Conforme seção 10.2 do how-to)
FILE_TO_SEND = "arquivo_teste.txt"
CHUNK_SIZE = 1024   # bytes por chunk

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(TIMEOUT)

def load_file_chunks(filename, chunk_size=1024):
    """Lê o arquivo em binário e retorna lista de chunks (bytes)."""
    # Implementação da seção 10.3
    with open(filename, "rb") as f:
        data = f.read()
    
    chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]
    return chunks

def send_and_wait_ack(pkt, server_addr):
    """
    Envia um pacote (com campo seq), aguarda ACK com timeout
    e retransmite até MAX_RETRIES.
    """
    seq = pkt["seq"]
    attempts = 0

    while attempts < MAX_RETRIES:
        attempts += 1
        send_time = time.time()
        sock.sendto(json.dumps(pkt).encode(), server_addr)
        print(f"[SEND] seq={seq}, tentativa={attempts}, type={pkt.get('type')}")

        try:
            data, _ = sock.recvfrom(2048)
            recv_time = time.time()
            rtt = recv_time - send_time

            # garantir que a transferência do arquivo binário utf-8 usando Base64 corretamente
            msg_str = data.decode('utf-8', errors='ignore')
            try:
                resp = json.loads(msg_str)
            except json.JSONDecodeError:
                print(f"[DEBUG] Recebido pacote que não é JSON válido. Ignorando.")
                continue
            
            # O servidor pode responder com "ack" ou "ack_chunk", desde que o seq bata
            if resp.get("seq") == seq:
                print(f"[ACK OK] seq={seq}, rtt={rtt:.3f}s, resp={resp}")
                return True, rtt
            else:
                print(f"[ACK INVÁLIDO] esperado seq={seq}, recebido={resp.get('seq')}")
        except socket.timeout:
            print(f"[TIMEOUT] seq={seq} (tentativa {attempts})")

    print(f"[FALHA] seq={seq} sem ACK após {MAX_RETRIES} tentativas")
    return False, None

def main():
    server_addr = (SERVER_IP, SERVER_PORT)

    # --- 1. Handshake ---
    seq = 0
    handshake = {
        "type": "handshake",
        "seq": seq,
        "msg": "hello-quic-sim"
    }

    print("[CLIENTE] Enviando handshake...")
    ok, rtt = send_and_wait_ack(handshake, server_addr)
    if not ok:
        print("[CLIENTE] Handshake falhou, encerrando.")
        return

    # --- 2. Envio de pacotes de dados simples ---
    print("\n[CLIENTE] Enviando pacotes de dados de teste...")
    for i in range(1, NUM_DATA_PKTS + 1):
        pkt = {
            "type": "data",
            "seq": i,
            "msg": f"pacote_data_{i}"
        }
        ok, rtt = send_and_wait_ack(pkt, server_addr)
        time.sleep(0.1)

    # --- 3. Envio de Arquivo (NOVO - Seção 10.4) ---
    print("\n[CLIENTE] Preparando envio de arquivo...")
    if not os.path.exists(FILE_TO_SEND):
        print(f"[CLIENTE] ERRO: Arquivo '{FILE_TO_SEND}' não encontrado.")
        print("Crie o arquivo com: dd if=/dev/urandom of=arquivo_teste.txt bs=1K count=50")
        return

    chunks = load_file_chunks(FILE_TO_SEND, CHUNK_SIZE)
    total = len(chunks)
    print(f"[CLIENTE] Enviando arquivo {FILE_TO_SEND} em {total} chunks.")

    seq_base = 1000 # Separar da sequência dos outros pacotes
    
    for i, raw_chunk in enumerate(chunks):
        seq = seq_base + i
        # Codifica binário para base64 string para poder ir no JSON
        b64_chunk = base64.b64encode(raw_chunk).decode()

        pkt = {
            "type": "file_chunk",
            "seq": seq,
            "total": total,
            "filename": os.path.basename(FILE_TO_SEND),
            "data": b64_chunk,
        }

        ok, rtt = send_and_wait_ack(pkt, server_addr)
        if not ok:
            print(f"[CLIENTE] Falha crítica ao enviar chunk seq={seq}. Abortando.")
            break
        
        # Pequena pausa para não saturar o log visualmente, se desejar
        # time.sleep(0.05)

    print("[CLIENTE] Fim da simulação QUIC-sim.")

if __name__ == "__main__":
    main()