# udp_server_final.py
#
# Servidor "QUIC-sim" baseado em UDP:
# - Simula atraso e perda
# - [NOVO] Recebe chunks de arquivo, armazena e reconstrói

import socket
import json
import random
import time
import base64
from collections import defaultdict

HOST = "0.0.0.0"
PORT = 4433

# Probabilidade de "perder" um pacote recebido (0.0 = 0%, 0.3 = 30%)
LOSS_PROB = 0.0
# Atraso máximo artificial na resposta (em segundos)
MAX_DELAY = 0.5

# Armazena chunks por arquivo: filename -> { "total": int, "chunks": {seq: bytes} }
files_state = defaultdict(lambda: {"total": None, "chunks": {}})

def rebuild_file(filename, file_info):
    """Reconstrói o arquivo a partir dos chunks recebidos (Seção 11.3)."""
    chunks_dict = file_info["chunks"]
    total = file_info["total"]
    
    # Ordena pelos seq
    ordered_seqs = sorted(chunks_dict.keys())
    
    if len(ordered_seqs) != total:
        print(f"[SERVIDOR] Aviso: Chunks recebidos ({len(ordered_seqs)}) != Total ({total})")

    output_name = f"recebido_{filename}"
    with open(output_name, "wb") as f:
        for seq in ordered_seqs:
            f.write(chunks_dict[seq])
            
    print(f"------------------------------------------------")
    print(f"[SERVIDOR] ARQUIVO RECONSTRUÍDO: {output_name}")
    print(f"------------------------------------------------")

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((HOST, PORT))

print(f"[SERVIDOR] QUIC-sim escutando em {HOST}:{PORT}")
print(f"[SERVIDOR] LOSS_PROB={LOSS_PROB}, MAX_DELAY={MAX_DELAY}s")

while True:
    try:
        data_bytes, addr = sock.recvfrom(8192) # Buffer generoso
    except Exception as e:
        # Se der erro no socket (ex: buffer overflow), apenas ignora
        continue

    now = time.time()

    # --- CORREÇÃO DA VARIÁVEL E DECODE ---
    # Usa data_bytes (correto) e errors='ignore' (seguro)
    decoded_data = data_bytes.decode('utf-8', errors='ignore')

    try:
        packet = json.loads(decoded_data)
    except json.JSONDecodeError:
        # Se recebeu lixo da rede (broadcast storm), ignora silenciosamente
        continue
    # -------------------------------------

    ptype = packet.get("type", "unknown")
    seq = packet.get("seq", "?")
    
    # ... O RESTANTE DO CÓDIGO PERMANECE IGUAL (Lógica de file_chunk etc) ...
    # (Copie a lógica do seu arquivo original a partir daqui: if random.random() < LOSS_PROB...)
    
    # Decisão de "perder" o pacote
    if random.random() < LOSS_PROB:
        print(f"  -> [DROP] simulando perda do pacote seq={seq}")
        continue

    if ptype == "file_chunk":
        filename = packet.get("filename", "arquivo.bin")
        total = packet["total"]
        b64_data = packet["data"]
        try:
            chunk_bytes = base64.b64decode(b64_data)
        except:
            continue
            
        file_info = files_state[filename]
        if file_info["total"] is None:
            file_info["total"] = total
        
        if seq not in file_info["chunks"]:
            file_info["chunks"][seq] = chunk_bytes

        print(f"[SERVIDOR] Chunk {len(file_info['chunks'])}/{total} recebido (seq={seq})")
        
        # Simula atraso
        time.sleep(random.uniform(0, MAX_DELAY))

        ack = {"type": "ack_chunk", "seq": seq}
        sock.sendto(json.dumps(ack).encode(), addr)

        if len(file_info["chunks"]) == file_info["total"]:
            rebuild_file(filename, file_info)
        continue

    # Resposta genérica (handshake/data)
    time.sleep(random.uniform(0, MAX_DELAY))
    response = {"type": "ack", "seq": seq}
    sock.sendto(json.dumps(response).encode(), addr)
    print(f"  -> [SEND] ACK seq={seq}")