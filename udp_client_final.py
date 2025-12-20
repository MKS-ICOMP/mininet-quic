# udp_client_final.py
#
# Cliente "QUIC-sim" baseado em UDP:
# - Envia handshake + vários pacotes "data"
# - Cada pacote tem seq
# - Mede RTT
# - Retransmite em caso de timeout

import socket
import json
import time

# Ajustar este IP para o IP do servidor visto de dentro do Mininet.
# Em laboratório simples, vamos começar assumindo que o servidor
# está em 10.0.0.1 (por ex: h1 mesmo, em outro terminal),
# e depois você pode adaptar para o host da VM.
SERVER_IP = "10.0.0.1"
SERVER_PORT = 4433

TIMEOUT = 1.0       # timeout para esperar ACK
MAX_RETRIES = 3     # retransmissões por pacote
NUM_DATA_PKTS = 5   # quantos pacotes de dados enviar

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(TIMEOUT)


def send_and_wait_ack(pkt, server_addr):
    """
    Envia um pacote (com campo seq), aguarda ACK com timeout
    e retransmite até MAX_RETRIES.
    Retorna (ok, rtt) onde rtt é o RTT medido ou None se falhou.
    """
    seq = pkt["seq"]
    attempts = 0

    while attempts < MAX_RETRIES:
        attempts += 1
        send_time = time.time()
        sock.sendto(json.dumps(pkt).encode(), server_addr)
        print(f"[SEND] seq={seq}, tentativa={attempts}")

        try:
            data, _ = sock.recvfrom(2048)
            recv_time = time.time()
            rtt = recv_time - send_time

            resp = json.loads(data.decode())
            if resp.get("type") == "ack" and resp.get("seq") == seq:
                print(f"[ACK OK] seq={seq}, rtt={rtt:.3f}s, resp={resp}")
                return True, rtt
            else:
                print(f"[ACK INVÁLIDO] resp={resp}")
        except socket.timeout:
            print(f"[TIMEOUT] seq={seq} (tentativa {attempts})")

    print(f"[FALHA] seq={seq} sem ACK após {MAX_RETRIES} tentativas")
    return False, None


def main():
    server_addr = (SERVER_IP, SERVER_PORT)

    # Handshake
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

    # Envio de pacotes de dados
    for i in range(1, NUM_DATA_PKTS + 1):
        pkt = {
            "type": "data",
            "seq": i,
            "msg": f"pacote_data_{i}"
        }
        ok, rtt = send_and_wait_ack(pkt, server_addr)
        time.sleep(0.5)

    print("[CLIENTE] Fim da simulação QUIC-sim.")

if __name__ == "__main__":
    main()
