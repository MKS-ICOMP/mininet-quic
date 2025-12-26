# analise.py
import re
import sys

def analisar_resultados(arquivo_log, tempo_total_s=None):
    try:
        with open(arquivo_log, 'r') as f:
            linhas = f.readlines()
    except FileNotFoundError:
        print(f"Erro: Arquivo '{arquivo_log}' não encontrado.")
        return

    rtts = []
    retransmissoes = 0
    acks_recebidos = 0
    
    # Padrões de Regex baseados no udp_client_final.py
    # Ex: [ACK OK] seq=1, rtt=0.492s, resp={...}
    padrao_rtt = re.compile(r"rtt=([0-9\.]+)s")
    # Ex: tentativa=2 (qualquer tentativa > 1 é retransmissão)
    padrao_tentativa = re.compile(r"tentativa=(\d+)")

    for linha in linhas:
        # Coleta RTT
        if "[ACK OK]" in linha:
            acks_recebidos += 1
            match = padrao_rtt.search(linha)
            if match:
                rtts.append(float(match.group(1)))
        
        # Coleta Retransmissões
        # Verifica se houve tentativas adicionais (>1)
        if "tentativa=" in linha:
            match = padrao_tentativa.search(linha)
            if match:
                tentativa = int(match.group(1))
                if tentativa > 1:
                    retransmissoes += 1
        elif "[TIMEOUT]" in linha:
            # Timeout geralmente implica numa retransmissão futura
            pass 

    # --- CÁLCULOS ---
    media_rtt = sum(rtts) / len(rtts) if rtts else 0.0
    taxa_retransmissao = 0.0
    total_envios = acks_recebidos + retransmissoes
    if total_envios > 0:
        taxa_retransmissao = (retransmissoes / total_envios) * 100

    print("-" * 40)
    print(f"RELATÓRIO DE ANÁLISE: {arquivo_log}")
    print("-" * 40)
    print(f"Pacotes Entregues (ACKs): {acks_recebidos}")
    print(f"RTT Médio por Chunk:      {media_rtt:.4f} s")
    print(f"Total Retransmissões:     {retransmissoes}")
    print(f"Taxa de Retransmissão:    {taxa_retransmissao:.2f}%")
    
    if tempo_total_s:
        # Throughput em pacotes/segundo (Aplicação)
        tput = acks_recebidos / float(tempo_total_s)
        print(f"Throughput (App):         {tput:.2f} chunks/s")
    else:
        print("Throughput:               (Informe o tempo total para calcular)")
    print("-" * 40)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 analise.py <arquivo_log> [tempo_total_segundos]")
    else:
        log = sys.argv[1]
        tempo = sys.argv[2] if len(sys.argv) > 2 else None
        analisar_resultados(log, tempo)