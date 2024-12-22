from socket import *

address = ('255.255.255.255', 12345)
s = socket(AF_INET, SOCK_DGRAM)
s.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
message = b'Gifts Collected!'
s.sendto(message, address)
s.close()
