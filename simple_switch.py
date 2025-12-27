# simple_switch_lower.py
# Força rota INFERIOR (s1-s3-s4) manipulando prioridades do STP.
# Mantém correções de "Table-Miss" e "Flood Nativo".

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp
from ryu.lib import stplib
from ryu.lib import dpid as dpid_lib

class SimpleSwitchRouteLower(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'stplib': stplib.Stp}

    def __init__(self, *args, **kwargs):
        super(SimpleSwitchRouteLower, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.stp = kwargs['stplib']
        self.port_state = {}

        # --- CONFIGURAÇÃO DE ROTA INFERIOR ---
        # Regra: Menor valor = Maior Prioridade no STP.
        # S1 (0x1000): Raiz.
        # S3 (0x2000): Prioridade ALTA. O STP vai preferir passar por aqui.
        # S2 (0x9000): Prioridade BAIXA (Pior). O STP vai bloquear este lado.
        # S4 (0x8000): Padrão.
        
        config = {
            dpid_lib.str_to_dpid('0000000000000001'): {'bridge': {'priority': 0x1000}},
            dpid_lib.str_to_dpid('0000000000000002'): {'bridge': {'priority': 0x9000}}, # Bloqueia s2
            dpid_lib.str_to_dpid('0000000000000003'): {'bridge': {'priority': 0x2000}}, # Prioriza s3
            dpid_lib.str_to_dpid('0000000000000004'): {'bridge': {'priority': 0x8000}}
        }
        self.stp.set_config(config)
        self.logger.info(">>> ROTA FORÇADA: S1 -> S3 -> S4 (INFERIOR) <<<")

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id is not None:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match, instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    def add_table_miss_flow(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        self.add_table_miss_flow(datapath)
        self.logger.info(f"⚪ Switch Conectado: {dpid_lib.dpid_to_str(datapath.id)}")

    @set_ev_cls(stplib.EventTopologyChange, MAIN_DISPATCHER)
    def _topology_change_handler(self, ev):
        dp = ev.dp
        match = dp.ofproto_parser.OFPMatch()
        mod = dp.ofproto_parser.OFPFlowMod(datapath=dp, command=dp.ofproto.OFPFC_DELETE,
                                           out_port=dp.ofproto.OFPP_ANY, out_group=dp.ofproto.OFPG_ANY,
                                           match=match)
        dp.send_msg(mod)
        self.add_table_miss_flow(dp)
        if dp.id in self.mac_to_port:
            self.mac_to_port[dp.id] = {}

    @set_ev_cls(stplib.EventPortStateChange, MAIN_DISPATCHER)
    def _port_state_change_handler(self, ev):
        dpid_str = dpid_lib.dpid_to_str(ev.dp.id)
        port_no = ev.port_no
        state = ev.port_state
        self.port_state.setdefault(dpid_str, {})
        self.port_state[dpid_str][port_no] = state
        
        if state == stplib.PORT_STATE_FORWARD:
             self.logger.info(f"🟢 LIBERADO: Switch {dpid_str} Porta {port_no}")
        elif state == stplib.PORT_STATE_BLOCK:
             self.logger.info(f"⛔ BLOQUEADO: Switch {dpid_str} Porta {port_no}")

    @set_ev_cls(stplib.EventPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == 0x88cc or eth.ethertype == 0x05dc: return

        dpid_str = dpid_lib.dpid_to_str(dpid)
        
        if dpid_str in self.port_state:
            state = self.port_state[dpid_str].get(in_port)
            if state == stplib.PORT_STATE_BLOCK or state == stplib.PORT_STATE_LISTEN:
                 return 
        
        src = eth.src
        dst = eth.dst
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        out_port = ofproto.OFPP_FLOOD
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]

        actions = []
        if out_port == ofproto.OFPP_FLOOD:
            actions.append(parser.OFPActionOutput(ofproto.OFPP_FLOOD))
        else:
            allow_out = True
            if dpid_str in self.port_state:
                dst_state = self.port_state[dpid_str].get(out_port)
                if dst_state == stplib.PORT_STATE_BLOCK or dst_state == stplib.PORT_STATE_LISTEN:
                    allow_out = False
            if allow_out:
                actions.append(parser.OFPActionOutput(out_port))

        if actions:
            if out_port != ofproto.OFPP_FLOOD:
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
            
            data = None
            if msg.buffer_id == ofproto.OFP_NO_BUFFER:
                data = msg.data
            out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                      in_port=in_port, actions=actions, data=data)
            datapath.send_msg(out)