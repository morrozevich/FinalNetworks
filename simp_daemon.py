import socket
import sys
import threading
import time
from header import SIMP_Socket


class SimpDaemon:
    def __init__(self, ip_address):
        self.ip_address = ip_address
        self.daemon_port = 7777
        self.client_port = 7778
        self.daemon_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client_address = None
        self.client_username = None
        self.client_connected = False
        self.other_daemon_ip = None
        self.message_sent = False
        self.ack_received = False
        self.other_daemon_connected = False
        self.pending_request = False
        self.pending_request_data = None
        self.fin_sent = False
        self.sequence_number = 0
        self.message_buffer = []
        self.accepted = None
        self.controlTypes = {
            b"\x00": "connect",
            b"\x01": "chat",
            b"\x02": "error",
            b"\x03": "quit",
            b"\x04": "connreq",
            b"\x05": "waitorstart",
            b'\x06': 'connestab',
            b'\x09': 'yesno',
            b'\x07': 'reask'
        }
        self.start()

    def start(self):
        # Bind the daemon and client sockets
        self.daemon_socket.bind((self.ip_address, self.daemon_port))
        print(f"Daemon-to-daemon socket running on IP {self.ip_address} and port {self.daemon_port}")
        self.client_socket.bind((self.ip_address, self.client_port))
        print(f"Daemon-to-client socket running on IP {self.ip_address} and port {self.client_port}")

        # Start threads to listen to client and daemon
        listen_to_client_thread = threading.Thread(target=self.listen_to_client)
        listen_to_client_thread.start()
        handshake_receiver_thread = threading.Thread(target=self.handshake_receiver)
        handshake_receiver_thread.start()
        message_forwarder_thread = threading.Thread(target=self.message_forwarder)
        message_forwarder_thread.start()

    def listen_to_client(self):
        # Listen for messages from the client
        while True:
            message, address = self.client_socket.recvfrom(4096)
            type = self.controlTypes[message[:1]]
            message = message[2:].decode()
            if type == "connect":
                # Handle connection request from client
                if self.client_connected:
                    message = b'\x02\x00' + "The daemon already connected to a client".encode()
                    self.client_socket.sendto(message, address)
                message = b'\x00\x00'
                self.client_socket.sendto(message, address)
                self.client_address = address
                self.client_connected = True
                message = b'\x00\x01' + "Please enter a username: ".encode()
                self.client_socket.sendto(message, self.client_address)
                username, address = self.client_socket.recvfrom(4096)
                username = username[2:].decode()
                self.client_username = username
                if not self.pending_request:
                    message = b'\x05\x01' + "Do you want to wait for connection or start one? [wait/start]: ".encode()
                    self.client_socket.sendto(message, self.client_address)
                    wait_or_start, address = self.client_socket.recvfrom(4096)
                    wait_or_start = wait_or_start[2:].decode()
                    if wait_or_start == "start":
                        message = b'\x05\x01' + "Enter the other daemon's IP address: ".encode()
                        self.client_socket.sendto(message, self.client_address)
                        other_daemon_ip, address = self.client_socket.recvfrom(4096)
                        other_daemon_ip = other_daemon_ip[2:].decode()
                        self.other_daemon_ip = other_daemon_ip
                        handshake_sender_thread = threading.Thread(target=self.handshake_sender)
                        handshake_sender_thread.start()
            elif type == "chat":
                # Handle chat message from client
                message = SIMP_Socket(
                    type='chat',
                    operation='message',
                    sequence='request',
                    user=self.client_username,
                    payload=message
                )
                self.message_buffer.append(message)
            elif type == "quit":
                # Handle quit message from client
                FIN = SIMP_Socket(
                    type='control',
                    operation='fin',
                    sequence='request',
                    user=self.client_username,
                    payload=''
                )
                self.send_packet_daemon(FIN.encode())
                self.fin_sent = True
            elif type == "yesno":
                # Handle yes/no response from client
                if self.pending_request:
                    if message == "y":
                        self.accepted = True
                    else:
                        self.accepted = False
            elif type == "reask":
                # Handle reask request from client
                message = b'\x05\x01' + "Do you want to wait for connection or start one? [wait/start]: ".encode()
                self.client_socket.sendto(message, self.client_address)
                wait_or_start, address = self.client_socket.recvfrom(4096)
                wait_or_start = wait_or_start[2:].decode()
                if wait_or_start == "start":
                    message = b'\x05\x01' + "Enter the other daemon's IP address: ".encode()
                    self.client_socket.sendto(message, self.client_address)
                    other_daemon_ip, address = self.client_socket.recvfrom(4096)
                    other_daemon_ip = other_daemon_ip[2:].decode()
                    self.other_daemon_ip = other_daemon_ip
                    handshake_sender_thread = threading.Thread(target=self.handshake_sender)
                    handshake_sender_thread.start()

    def listen_to_daemon(self):
        # Listen for messages from the other daemon
        while True:
            data, address = self.daemon_socket.recvfrom(4096)
            rec = SIMP_Socket()
            rec.decode(data)
            print("---------------------------------")
            print("Packet received from other daemon")
            rec.printData()
            print("---------------------------------")
            if rec.operation == "message":
                # Forward chat message to client and send ack to other daemon
                message = b'\x01\x00' + rec.payload.encode()
                self.client_socket.sendto(message, self.client_address)
                ack = SIMP_Socket(
                    type='control',
                    operation='ack',
                    sequence='response',
                    user=self.client_username,
                    payload=''
                )
                self.daemon_socket.sendto(ack.encode(), (self.other_daemon_ip, self.daemon_port))
            elif rec.operation == "fin":
                # Handle FIN message from other daemon
                ACK = SIMP_Socket(
                    type='control',
                    operation='ack',
                    sequence='response',
                    user=self.client_username,
                    payload=''
                )
                ACK_binary = ACK.encode()
                self.daemon_socket.sendto(ACK_binary, (self.other_daemon_ip, self.daemon_port))
                message = b'\x03\x00' + rec.payload.encode()
                self.client_socket.sendto(message, self.client_address)
                self.client_connected = False
                self.client_address = None
                self.other_daemon_ip = None
                handshake_receiver_thread = threading.Thread(target=self.handshake_receiver)
                handshake_receiver_thread.start()
            elif rec.operation == "ack":
                # Handle ACK message from other daemon
                if self.fin_sent:
                    message = b'\x03\x00'
                    self.client_socket.sendto(message, self.client_address)
                    self.client_connected = False
                    self.client_address = None
                    self.other_daemon_ip = None
                    self.other_daemon_connected = False
                    self.fin_sent = False
                    handshake_receiver_thread = threading.Thread(target=self.handshake_receiver)
                    handshake_receiver_thread.start()
                    break
                if self.message_sent:
                    self.ack_received = True
                    self.message_sent = False
            elif rec.operation == "syn" and self.other_daemon_connected:
                # Handle SYN message when already connected
                ERR = SIMP_Socket(
                    type='control',
                    operation='error',
                    sequence='response',
                    user=self.client_username,
                    payload="User already in another chat"
                )
                self.daemon_socket.sendto(ERR.encode(), address)
                FIN = SIMP_Socket(
                    type='control',
                    operation='fin',
                    sequence='response',
                    user=self.client_username,
                    payload="User already in another chat"
                )
                self.daemon_socket.sendto(FIN.encode(), address)


#The message_forwarder method handles detecting lost datagrams using the sequence number and the timeout.
#In case it does not receive a reply after a specified amount of
#time (default: 5 seconds), it will retransmit the datagram with the same sequence number.
# After the ACK comes, it will transmit the next datagram with the next sequence number (0 or 1).
    def message_forwarder(self):
        while True:
            if len(self.message_buffer) > 0:
                # picks the requeued datagram from the message_buffer
                message = self.message_buffer.pop(0)
                message.sequence = 'request' if self.sequence_number == 0x00 else 'response'
                self.sequence_number = 0x01 if self.sequence_number == 0x00 else 0x00
                self.daemon_socket.sendto(message.encode(), (self.other_daemon_ip, self.daemon_port))
                self.message_sent = True
                print("Message sent to other daemon")
                message.printData()
                timer = 0
                while not self.ack_received and timer < 5:
                    time.sleep(0.01)
                    timer += 0.01

                if timer >= 5:
                    print("Message not acknowledged, resending")
                    self.message_buffer.insert(0, message)  #Requeues the same datagram object to send again
                    continue

                print("Message acknowledged")
                self.ack_received = False

    def send_packet_daemon(self, data):
        # Send packet to the other daemon if buffer is empty
        if not self.message_buffer:
            self.daemon_socket.sendto(data, (self.other_daemon_ip, self.daemon_port))

    def handshake_sender(self):
        # Initiate handshake by sending SYN
        SYN = SIMP_Socket(
            type='control',
            operation='syn',
            sequence='request',
            user=self.client_username,
            payload=''
        )
        SYN_binary = SYN.encode()
        self.daemon_socket.sendto(SYN_binary, (self.other_daemon_ip, self.daemon_port))

    def handshake_receiver(self):
        # Handle incoming handshake requests
        print("Waiting for handshake")
        while True:
            data, address = self.daemon_socket.recvfrom(4096)
            rec = SIMP_Socket()
            rec.decode(data)
            #The receiver processes the SYN and replies with a control datagram that combines SYN and ACK.
            if rec.type == "control" and rec.operation == "syn":
                print("syn received")
                self.pending_request = True
                self.pending_request_data = (rec.user, address)
                # waits for the client to connect.
                while not self.client_connected:
                    time.sleep(0.01)
                    pass
                if self.client_connected:
                    message = b'\x04\x01' + f"Request from user {self.pending_request_data[0]} address: {self.pending_request_data[1][0]}:{self.pending_request_data[1][1]}. Do you want to accept? [y/n]: ".encode()
                    self.client_socket.sendto(message, self.client_address)
                    self.other_daemon_ip = address[0]
    # It then waits for the client's decision
                    while self.accepted is None:
                        time.sleep(0.01)
                        pass
                    if self.accepted:
                        self.accepted = None
                    else:
                        FIN = SIMP_Socket(
                            type='control',
                            operation='fin',
                            sequence='response',
                            user=self.client_username,
                            payload='Error: The other client declined your request'
                        )
                        FIN_binary = FIN.encode()
                        print("Fin sent")
                        self.daemon_socket.sendto(FIN_binary, (self.other_daemon_ip, self.daemon_port))
                        handshake_receiver_thread = threading.Thread(target=self.handshake_receiver)
                        handshake_receiver_thread.start()
                        self.accepted = None
                        self.pending_request = False
                        break
                    #If Client Accepts the connection then creates and sends a combined SYN + ACK
                    self.pending_request = False
                    SYN = SIMP_Socket(
                        type='control',
                        operation='syn',
                        sequence='response',
                        user=self.client_username,
                        payload=''
                    )
                    ACK = SIMP_Socket(
                        type='control',
                        operation='ack',
                        sequence='response',
                        user=self.client_username,
                        payload=''
                    )
                    SYN_binary = SYN.encode()
                    ACK_binary = ACK.encode()
                    SYN_ACK_binary = bytearray(b1 | b2 for b1, b2 in zip(ACK_binary, SYN_binary))
                    self.daemon_socket.sendto(bytes(SYN_ACK_binary), (self.other_daemon_ip, self.daemon_port))
                    print("synack sent")
            if rec.type == "control" and rec.operation == "ack":
                # Connection established, notify client
                self.other_daemon_connected = True
                print("ACK received")
                message = b'\x06\x00' + "Connection established".encode()
                self.client_socket.sendto(message, self.client_address)
                listen_to_daemon_thread = threading.Thread(target=self.listen_to_daemon)
                listen_to_daemon_thread.start()
                break
            if rec.type == "control" and rec.operation == "fin":
                # connection declined
                print("FIN received, connection was declined")
                message = b'\x02\x00' + rec.payload.encode()
                self.client_socket.sendto(message, self.client_address)
                self.client_connected = False
                self.client_address = None
                self.other_daemon_ip = None
                handshake_receiver_thread = threading.Thread(target=self.handshake_receiver)
                handshake_receiver_thread.start()
                break
            if rec.type == "control" and rec.operation == "synack":
                # Send final ACK to establish connection
                ACK = SIMP_Socket(
                    type='control',
                    operation='ack',
                    sequence='request',
                    user=self.client_username,
                    payload=''
                )
                ACK_binary = ACK.encode()
                self.daemon_socket.sendto(ACK_binary, (self.other_daemon_ip, self.daemon_port))
                self.other_daemon_connected = True
                print("sending ack")
                message = b'\x06\x00' + "Connection established".encode()
                self.client_socket.sendto(message, self.client_address)
                listen_to_daemon_thread = threading.Thread(target=self.listen_to_daemon)
                listen_to_daemon_thread.start()
                break
            if rec.type == "control" and rec.operation == "error":
                # Handle error message
                message = b'\x02\x00' + rec.payload.encode()
                self.client_socket.sendto(message, self.client_address)
                self.client_connected = False
                self.client_address = None
                self.other_daemon_ip = None
                handshake_receiver_thread = threading.Thread(target=self.handshake_receiver)
                handshake_receiver_thread.start()
                break


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 simp_daemon.py <ip_address>")
        sys.exit(1)

    daemon_ip = sys.argv[1]
    daemon = SimpDaemon(daemon_ip)
