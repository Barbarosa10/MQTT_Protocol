from MQTT_constants import *
import socket
import struct
import random
import sys
import threading
import time

class MQTTPacket:
    def __init__(self, control_type: int, RETAIN=0, QoS=0, DUP=0) -> None:
        self.control_type = control_type
        self.DUP = DUP
        self.QoS = QoS
        self.RETAIN = RETAIN
        self.remaining_packet=b""

    def from_bytes(self, packet: bytes):
        self.packet = packet
        self.control_type = packet[0] >> 4
        self.DUP = (packet[0] & 0b1000) >> 3
        self.QoS = (packet[0] & 0b110) >> 1
        self.RETAIN = packet[0] & 1
        tmp = 0
        for i in range(1,5):
            tmp += (packet[i] & 0x7f) << ((i-1)*7)
            if(packet[i] & 0x80 == 0):
                break

        self.remaining_len = tmp
        self.packet_size = self.remaining_len + i
        self.var_head_start = i+1

        return self

    def get_packet_id(self):
        tmp = (self.packet[self.var_head_start] << 8 | self.packet[self.var_head_start+1] )
        return tmp

    def set_remaining_packet(self, pac: bytes) -> None:
        self.remaining_packet = pac

    def get_packet(self):
        first_part = self.control_type << 4
        first_part |= ( self.DUP << 3 | self.QoS << 1 | self.RETAIN)
        #second part -> TBD
        if(len(self.remaining_packet) > 256):
            second_part = struct.pack("!h", len(self.remaining_packet))
        else:
            second_part = bytes([len(self.remaining_packet)])

        self.packet = bytes([first_part]) + second_part + self.remaining_packet

        return self.packet  

    def get_topic_and_message(self):
        if(self.control_type != PUBLISH):
            return "",""
        topic_len = self.packet[self.var_head_start]<<8 | self.packet[self.var_head_start+1]
        #print("TOPIC LEN: " + str(topic_len))
        topic = self.packet[self.var_head_start+2:self.var_head_start+2+topic_len]

        property_len = 0
        for i in range(0,4):
            property_len += (self.packet[self.var_head_start+2+topic_len+(2*(self.QoS != 0))+i] & 0x7f) << (i*7)
            if(self.packet[self.var_head_start+2+topic_len+(2*(self.QoS != 0))+i] & 0x80 == 0):
                break
        #print("PROPERTY LEN: " + str(property_len))
        payload_len = self.remaining_len - (2+topic_len+(2*(self.QoS != 0))+i+1)
        #print("Payload len: " + str(payload_len))
        payload = self.packet[(self.var_head_start+2+topic_len+(2*(self.QoS != 0))+i+1) : (self.var_head_start+2+topic_len+(2*(self.QoS != 0))+i+payload_len+1)]
        return topic, payload

class Client:
    connection = 0
    packetID = []
    publishedPackets = []
    received_packets: MQTTPacket = []
    listen_thread: threading.Thread = 0
    lock: threading.Lock = threading.Lock()
    timer: threading.Timer = 0
    running = 0

    def __init__(self, ip, port, keep_alive = 0, username="", password="") -> None:
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.keep_alive = keep_alive
        

    def connect_socket(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connection=1
        try:
            self.s.connect((self.ip, self.port))
        except:
            self.connection = 0

    def connect(self, will_topic="", will_payload=""):

        pac = MQTTPacket(CONNECT, QoS = 0)

        CLEAN_START = 1
        WILL_RETAIN = 0
        WILL_QOS = 0
        WILL_FLAG = (will_topic != "")

        packet = b""
        # Protocol Name + Protocol Version
        packet += b"\x00\x04MQTT" + b"\x05"
        packet += bytes([ (self.username != "")<<7 | (self.password != "") << 6 | WILL_RETAIN << 5 | WILL_QOS << 3 | WILL_FLAG << 2 | CLEAN_START << 1 ])
        packet += struct.pack("!h", self.keep_alive)

        poss_str = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        client_id = b''.join(bytes([random.choice(poss_str)]) for i in range(random.randint(1, 23)))

        packet += b"\x00" # Properties length
        
        packet += struct.pack("!h", len(client_id))
        packet += client_id

        packet += b"\x00" # Will properties length


        if(WILL_FLAG):
            packet += struct.pack("!h", len(will_topic)) + will_topic.encode("utf-8")
            packet += struct.pack("!h", len(will_payload)) + will_payload.encode("utf-8")

        if(self.username != ""):
            packet += struct.pack("!h", len(self.username)) + self.username.encode("utf-8")
            packet += struct.pack("!h", len(self.password)) + self.password.encode("utf-8")
        # Payload
        # ClientID
        pac.set_remaining_packet(packet)

        self.s.sendall(pac.get_packet())

        connack = self.s.recv(1024)
        while(len(connack) == 0):
            connack = self.s.recv(1024)

        if(connack[3] != 0):
            print("Connection error: " + str(connack[3]))
            self.s.close()
            sys.exit(0)

        self.listen_thread = threading.Thread(target=self.listen_for_messages )
        self.running = 1
        self.timer = threading.Timer(self.keep_alive, self.ping)
        self.timer.start()
        self.listen_thread.start()


    def publish(self, topic, message, qos=0):
        mqttPacket = MQTTPacket(PUBLISH, QoS=qos)
        packet = b""
        # Topic Length + Topic + Packet Identifier
        packet += struct.pack("!h", len(topic))
        packet += topic.encode('utf-8')

        if(mqttPacket.QoS > 0):
            id = 1
            while(id in self.packetID):
                id += 1
            self.packetID.append(id)
            packet += struct.pack("!h", id)
        packet += b"\x00"
        # Payload
        packet += message.encode('utf-8')

        mqttPacket.set_remaining_packet(packet)

        self.send_packet(mqttPacket.get_packet())

        #Receive packets in case of QoS = 1 or 2
        if(mqttPacket.QoS == 1):
            puback = self.get_packet_from_list(PUBACK, id)
            while(puback == None):
                self.send_packet(mqttPacket.get_packet())
                puback = self.get_packet_from_list(PUBACK, id)

            puback = puback.packet
            if(not(puback[1] == 2 or puback[4]==0)):
                self.publish(topic, message)
            if(id in self.packetID):
                self.packetID.remove(id)

        elif(mqttPacket.QoS == 2):

            pubrec = self.get_packet_from_list(PUBREC, id)
            while(pubrec == None):
                self.send_packet(mqttPacket.get_packet())
                pubrec = self.get_packet_from_list(PUBREC, id)

            pubrec = pubrec.packet
            
            mqttpacket = MQTTPacket(PUBREL, QoS=1 )
            check=1
            if(len(pubrec) > 4):
                check = pubrec[4]
            if(pubrec[1] == 2 or check==0):
                pubrel = b""
                pubrel += bytes([pubrec[2]]) + bytes([pubrec[3]])
                mqttpacket.set_remaining_packet(pubrel)
                self.send_packet(mqttpacket.get_packet())
                #pubcomp = self.s.recv(1024)
                pubcomp = self.get_packet_from_list(PUBCOMP, id)
                while(pubcomp == None):
                    self.send_packet(mqttpacket.get_packet())
                    pubcomp = self.get_packet_from_list(PUBCOMP, id)
                pubcomp = pubcomp.packet
                check2 = 1
                if(len(pubcomp) > 4):
                    check2 = pubcomp[4]
                if(not (pubcomp[1] == 2 or check2 == 0)):
                    self.publish(topic, message)
                if(id in self.packetID):
                    self.packetID.remove(id)
            else:
                self.publish(topic, message)

    def ping(self):
        pac = MQTTPacket(PINGREQ, QoS=0)
        self.send_packet(pac.get_packet())

        pac = self.get_packet_from_list(PINGRESP)
        if(pac == None):
            print("SERVER DED")
            self.s.close()
            sys.exit(0)

    def listen_for_messages(self):
        while(self.running):
            pac = self.s.recv(1024)
            if(len(pac) == 0):
                continue
            tmp = MQTTPacket(0).from_bytes(pac)
            if(tmp.remaining_len > 1024):
                pac += self.s.recv(tmp.packet_size-1024)
            tmp = MQTTPacket(0).from_bytes(pac)
            if(tmp.control_type==PUBLISH):
                topic, message = tmp.get_topic_and_message()
                self.publishedPackets.append([topic, message])
            else:
                self.lock.acquire()
                self.received_packets.append(tmp)
                self.lock.release()

    def get_packet_from_list(self, control_type: int, packetID: int = -1, timeout: int = 0.2) -> MQTTPacket:
        pac = None
        for i in range(2):
            for packet in self.received_packets:
                if(packet.control_type == control_type and (packetID == -1 or packet.get_packet_id() == packetID)):
                    pac = packet
                    self.lock.acquire()
                    self.received_packets.remove(pac)
                    self.lock.release()
                    break
            if pac == None and i==0:
                time.sleep(timeout)


        return pac

    
    def subscribe(self, topic, maxQoS=2):
        mqttPacket = MQTTPacket(SUBSCRIBE, QoS=1)
        packet = b""
        id = 1

        while(id in self.packetID):
            id += 1

        self.packetID.append(id)
        #Packet ID
        packet += struct.pack("!h", id)

        #Properties length
        packet += b'\x00'

        #Topic + length
        packet += struct.pack("!h", len(topic))
        packet += topic.encode("utf-8")

        RETAIN_HANDLE = 2
        NO_LOCAL = 1
        RAP = 0
        packet += bytes([maxQoS | NO_LOCAL << 2 | RAP << 3 | RETAIN_HANDLE << 4])

        mqttPacket.set_remaining_packet(packet)
        self.send_packet(mqttPacket.get_packet())
        rec_pac = self.get_packet_from_list(SUBACK, id)
        if(rec_pac.control_type == SUBACK and rec_pac.get_packet_id() == id):
            print("Subscribed")
    
    def unsubscribe(self, topic):
        mqttPacket = MQTTPacket(UNSUBSCRIBE, QoS=1)
        packet = b""
        id = 1
        while(id in self.packetID):
            id += 1

        self.packetID.append(id)
        #Packet ID
        packet += struct.pack("!h", id)

        #Properties length
        packet += b'\x00'

        #Topic + length
        packet += struct.pack("!h", len(topic))
        packet += topic.encode("utf-8")

        mqttPacket.set_remaining_packet(packet)

        self.send_packet(mqttPacket.get_packet())
        rec_pac = self.get_packet_from_list(UNSUBACK, id)
        if(rec_pac.control_type == UNSUBACK and rec_pac.get_packet_id() == id):
            print("UnSubscribed")

    def disconnect(self, lastWill):
        mqttPacket = MQTTPacket(DISCONNECT, QoS = 0)
        packet = b""
        if(lastWill == True):
            packet += b'\x04'
        else:
            packet += b'\x00'
        packet += b'\x00'

        mqttPacket.set_remaining_packet(packet)

        self.timer.cancel()      
        self.s.sendall(packet)

    def send_packet(self, packet):
        self.s.sendall(packet)
        self.timer.cancel()
        self.timer = threading.Timer(self.keep_alive, self.ping)
        self.timer.start()