import os
import socket
import sys
import threading
import time
import msvcrt
class SimpClient:
    def __init__(self, ip_address):
        self.daemon_ip = ip_address
        self.daemon_port = 7778
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.controlTypes = {
            b"\x00": "connect",
            b"\x01": "chat",
            b"\x02": "error",
            b"\x03": "quit",
            b"\x04": "connreq",
            b'\x06': 'connestab',
            b"\x05": "waitorstart"
        }
        self.waiting_for_reply = False
        self.start()

    def split_data(self, data):
        type = self.controlTypes[data[:1]]
        wait_for_response = (data[1:2] == b"x01")
        message = data[2:].decode()
        return type, wait_for_response, message

    def start(self):
        message = b'\x00\x01'
        self.client_socket.sendto(message, (self.daemon_ip, self.daemon_port))
        msg, address = self.client_socket.recvfrom(4096)
        type, wait_for_response, msg = self.split_data(msg)
        if type == "error":
            print(msg)
            sys.exit(1)
        print("Connected to daemon successfully!")
        msg, address = self.client_socket.recvfrom(4096)
        type, wait_for_response, msg = self.split_data(msg)
        username = b'\x00\x01' + input(msg).encode()
        self.client_socket.sendto(username, (self.daemon_ip, self.daemon_port))
        listen_to_daemon_thread = threading.Thread(target=self.listen_to_daemon)
        listen_to_daemon_thread.start()

    def listen_to_daemon(self):
        while True:
            data, address = self.client_socket.recvfrom(4096)
            type = self.controlTypes[data[:1]]
            message = data[2:].decode()
            if type == "connreq":
                answer = input(message)
                message = b'\x09\x01' + answer.encode()
                self.client_socket.sendto(message, (self.daemon_ip, self.daemon_port))
                if answer == "y":
                    pass
                elif answer == "n":
                    message = b'\x07'
                    self.client_socket.sendto(message, (self.daemon_ip, self.daemon_port))
                    pass
            elif type == "waitorstart":
                answer = input(message)
                message = b'\x05\x00' + answer.encode()
                self.client_socket.sendto(message, (self.daemon_ip, self.daemon_port))
                if answer == "start":
                    msg, address = self.client_socket.recvfrom(4096)
                    type, wait_for_response, msg = self.split_data(msg)
                    other_daemon_ip = input(msg)
                    message = b'\x05\x00' + other_daemon_ip.encode()
                    self.client_socket.sendto(message, (self.daemon_ip, self.daemon_port))
                elif answer == "wait":
                    print("Waiting for connection...")
            elif type == "error":
                print(message)
                print("Closing connection")
                sys.exit(1)
            elif type == "connestab":
                print("Connection established!")
                print('Type your message below (send "q" to disconnect) then wait: ')
                send_chat_message_to_daemon_thread = threading.Thread(target=self.send_chat_message_to_daemon)
                send_chat_message_to_daemon_thread.start()
            elif type == "chat":
                print(f"Other user wrote \"{message}\" type your message below and wait for response: ")
                self.waiting_for_reply = False
            elif type == "quit":
                print("\nYou or the another person just terminated the connection.")
                os._exit(0)

    def suppress_input(self):
        try:
            import termios, tty  # For Unix/Linux systems
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)  # Disable line buffering
                while self.waiting_for_reply:
                    time.sleep(0.5)  # Block input during this time
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)  # Restore terminal settings
        except ImportError:
            import msvcrt  # For Windows systems
            while self.waiting_for_reply:
                if msvcrt.kbhit():  # Detect if a key was pressed
                    msvcrt.getch()  # Clear the key press
                time.sleep(0.5)

    def send_chat_message_to_daemon(self):
        sequence_number = 0x00
        while True:

            if not self.waiting_for_reply:
                print("Ready to accept user input.")  # Debug: Input ready
                sys.stdout.flush()  # Ensure prompt appears immediately

                message = input()
                if message == "q":
                    print("Closing connection")
                    message = b'\x03\x00'
                    self.client_socket.sendto(message, (self.daemon_ip, self.daemon_port))
                    break
                self.waiting_for_reply = True
                sequence = b'\x00' if sequence_number == 0x00 else b'\x01'
                sequence_number = 0x01 if sequence_number == 0x00 else 0x00
                self.client_socket.sendto(b'\x01' + sequence + message.encode(), (self.daemon_ip, self.daemon_port))
            else:
                self.suppress_input()



if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 simp_client.py <ip_address>")
        sys.exit(1)

    daemon_ip = sys.argv[1]
    daemon = SimpClient(daemon_ip)
