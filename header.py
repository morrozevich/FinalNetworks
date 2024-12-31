import struct

class SIMP_Socket:        #Header implementation
    def __init__(self, type=None, operation=None, sequence=None, user=None, length=None, payload=None):
        self.type = type
        self.operation = operation
        self.sequence = sequence
        self.user = user
        self.length = length
        self.payload = payload

    def encode(self):
        if self.type == 'control':
            type_binary = struct.pack('B', 0x01)
            # when the type is 'chat' (which translates to 0x02), the payload contains the chat message to be sent.
        elif self.type == 'chat':
            type_binary = struct.pack('B', 0x02)
        else:
            raise Exception('Invalid type')
#Control datagrams: ERR (0x01), SYN (0x02), ACK (0x04), FIN (0x08).
        if self.type == 'control':
            #If Type == 0x01 (control datagram) and Operation == 0x01 (error)
            if self.operation == 'error':
                operation_binary = struct.pack('B', 0x01)
            elif self.operation == 'syn':
                operation_binary = struct.pack('B', 0x02)
            elif self.operation == 'ack':
                operation_binary = struct.pack('B', 0x04)
            elif self.operation == 'fin':
                operation_binary = struct.pack('B', 0x08)
            else:
                raise Exception('Invalid operation')
        elif self.type == 'chat': #If Type == 0x02 (chat datagram): field Operation takes the constant value 0x01.
            operation_binary = struct.pack('B', 0x01)
        else:
            raise Exception('Invalid operation')
        # helps differentiate between new datagrams and retransmissions
        if self.sequence == 'request':
            sequence_binary = struct.pack('B', 0x00)
        elif self.sequence == 'response':
            sequence_binary = struct.pack('B', 0x01)
        else:
            raise Exception('Invalid sequence')

        # User (32 bytes): user name encoded as an ASCII string.
        user_binary = self.user.encode('ascii')
        user_binary = user_binary.ljust(32, b'\x00')

        #  If there is a payload (e.g., error message)
        payload_binary = self.payload.encode('ascii') # a human-readable error message as an ASCII string / the contents of the chat message to be sent.

        self.length = len(payload_binary)

        # Length (4 bytes): length of the datagram payload in bytes.
        length_bytes = self.length.to_bytes(4, 'big')

        return type_binary + operation_binary + sequence_binary + user_binary + length_bytes + payload_binary

    def decode(self, bytestream):
        # Convert type to string
        if bytestream[0] == 0x01:
            self.type = 'control'
        elif bytestream[0] == 0x02:
            self.type = 'chat'
        else:
            raise Exception('Invalid type')

        # Convert operation to string
        if self.type == 'control':
            #If Type == 0x01 (control datagram) and Operation == 0x01 (error)
            if bytestream[1] == 0x01:
                self.operation = 'error'
            elif bytestream[1] == 0x02:
                self.operation = 'syn'
            elif bytestream[1] == 0x04:
                self.operation = 'ack'
            elif bytestream[1] == 0x08:
                self.operation = 'fin'
            elif bytestream[1] == 0x06:
                self.operation = 'synack'
            else:
                self.operation = 'unknown'
        elif self.type == 'chat':
            self.operation = 'message'
        else:
            raise Exception('Invalid operation')
        if bytestream[2] == 0x00:
            self.sequence = 'request'
        elif bytestream[2] == 0x01:
            self.sequence = 'response'
        else:
            raise Exception('Invalid sequence')
        self.user = bytestream[3:35].decode('ascii').strip('\x00')
        self.length = int.from_bytes(bytestream[35:39], 'big')

        # The payload is extracted starting from the 40th byte to the end of the byte stream and is decoded as an ASCII string
        self.payload = bytestream[39:].decode('ascii')

    def printData(self):
        print('Type: {}'.format(self.type))
        print('Operation: {}'.format(self.operation))
        print('Sequence: {}'.format(self.sequence))
        print('User: {}'.format(self.user))
        print('Length: {}'.format(self.length))
        print('Payload: {}'.format(self.payload))
