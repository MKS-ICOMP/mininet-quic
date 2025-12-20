# udp_server_final.py
#
# Servidor "QUIC-sim" baseado em UDP:
# - Porta 4433 (porta típica para testes QUIC)
# - Simula atraso de rede
# - Simula perda de pacotes
# - Responde com ACK contendo o seq

import socket
import json
import random
import time

HOST = "0.0.0.0"
PORT = 4433

# Probabilidade de "perder" um pacote recebido (0.3 = 30%)
LOSS_PROB = 0.0

# Atraso máximo artificial na resposta (em segundos)
MAX_DELAY = 0.5

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((HOST, PORT))

print(f"[SERVIDOR] QUIC-sim escutando em {HOST}:{PORT}")
print(f"[SERVIDOR] LOSS_PROB={LOSS_PROB}, MAX_DELAY={MAX_DELAY}s")

while True:
    data, addr = sock.recvfrom(2048)
    now = time.time()
    try:
        packet = json.loads(data.decode())
    except Exception:
        packet = {"type": "unknown", "raw": data.decode(errors="ignore")}

    ptype = packet.get("type", "unknown")
    seq = packet.get("seq", "?")
    msg = packet.get("msg", "")

    print(f"[RECV {now:.3f}] de {addr} -> type={ptype}, seq={seq}, msg={msg}")

    # Decisão de "perder" o pacote
    if random.random() < LOSS_PROB:
        print(f"  -> [DROP] simulando perda do pacote seq={seq}")
        continue

    # Atraso artificial
    delay = random.uniform(0, MAX_DELAY)
    time.sleep(delay)

    response = {
        "type": "ack",
        "seq": seq,
        "info": f"ack-from-server (delay={delay:.3f}s)"
    }
    resp_bytes = json.dumps(response).encode()
    sock.sendto(resp_bytes, addr)

    print(f"  -> [SEND] ACK seq={seq} para {addr} (delay={delay:.3f}s)")
