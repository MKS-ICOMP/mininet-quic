# simple_switch.py
#
# Controlador SDN simples usando Ryu e OpenFlow 1.3.
# Implementa um "learning switch":
# - aprende MAC -> porta
# - instala fluxos para evitar enviar tudo ao controlador

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet


class SimpleSwitch13(app_manager.RyuApp):
    # Usaremos OpenFlow 1.3
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        # Tabela: dpid -> {mac: porta}
        self.mac_to_port = {}

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        """Instala uma regra de fluxo no switch."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        if buffer_id is not None:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                buffer_id=buffer_id,
                priority=priority,
                match=match,
                instructions=inst,
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                priority=priority,
                match=match,
                instructions=inst,
            )

        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Chamado quando o switch conecta ao controlador.

        Aqui instalamos a regra "table-miss": qualquer pacote que não
        bater em nenhuma regra será enviado ao controlador.
        """
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Match vazio = qualquer pacote
        match = parser.OFPMatch()
        # Ação: mandar para o controlador
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]

        # Prioridade 0 (mais baixa)
        self.add_flow(datapath, 0, match, actions)

        self.logger.info("Table-miss instalada para switch %s", datapath.id)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """Tratamento de pacotes enviados ao controlador (packet-in)."""
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        in_port = msg.match['in_port']

        # Decodificar o pacote
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        # Ignora LLDP (usado para descoberta de topologia)
        if eth.ethertype == 0x88cc:
            return

        dst = eth.dst
        src = eth.src

        # Inicializa tabela para este switch se ainda não existir
        self.mac_to_port.setdefault(dpid, {})

        self.logger.info("PACKET_IN dpid=%s src=%s dst=%s in_port=%s",
                         dpid, src, dst, in_port)

        # Aprende MAC de origem -> porta de entrada
        self.mac_to_port[dpid][src] = in_port

        # Se já conhecemos a MAC de destino, encaminhamos diretamente
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            # Caso contrário, flood
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Se já sabemos a porta de saída e não é FLOOD, instalamos fluxo
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)

            # Se o switch já possui o pacote em buffer, passamos o buffer_id
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, 1, match, actions)

        # Envia o pacote atual (packet-out)
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        else:
            data = None

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)
