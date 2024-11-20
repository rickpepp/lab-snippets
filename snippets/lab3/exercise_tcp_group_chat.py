import threading
import pytest
import hypothesis.strategies as st
from hypothesis import given
import ipaddress
import string
import socket
import sys
import json
import logging
import time
import psutil


def local_ips():
    for interface in psutil.net_if_addrs().values():
        for addr in interface:
            if addr.family == socket.AF_INET:
                    yield addr.address

# Functions
def validateIpAddress(ip: str):
    try:
        value = ipaddress.ip_address(ip)
        return isinstance(value, ipaddress.IPv4Address)
    except ValueError:
        return ip == 'localhost'
    
# Copied from __init__ lab3
# Added check on ':' char, because accepted only x.x.x.x or x.x.x.x:p
# Can raise InvalideIpAddress or InvalidPortRange
def obtainIpaddressFromString(ip='0.0.0.0:0', port=None):
    ip = ip.strip()
    if ip.count(':') != 1 and ip.count(':') != 0:
        raise InvalidIpAddress
    if ':' in ip:
        ip, p = ip.split(':')
        try:
            p = int(p)
        except ValueError:
            raise InvalidIpAddress
        port = port or p
    if port is None:
        port = 0
    if (port not in range(0, 65536)):
        raise InvalidPortRange
    if (not isinstance(ip, str)):
        raise InvalidIpAddress("Ip is not a string")
    if (not validateIpAddress(ip)):
        raise InvalidIpAddress
    if (ip == 'localhost'):
        ip = '127.0.0.1'
    return ip, port



class InvalidPortRange(Exception):
    def __init__(self, message: str = None):
        if (isinstance(message,str) and message != None):
            super().__init__(message)
        else:
            super().__init__("Port number must be in the range 0-65535")

class InvalidIpAddress(Exception):
    def __init__(self, message: str = None):
        if (isinstance(message,str) and message != None):
            super().__init__(message)
        else:
            super().__init__("Invalid IP address, must be a string (x.x.x.x:p or x.x.x.x) and IPv4 type")

class InvalidMessage(Exception):
    def __init__(self, message: str = None):
        if (isinstance(message,str) and message != None):
            super().__init__(message)
        else:
            super().__init__("Message args are not correct")

class ImpossibleToConnectToPeer(Exception):
    def __init__(self, message: str = None):
        if (isinstance(message,str) and message != None):
            super().__init__(message)
        else:
            super().__init__("Impossible to connect with the peer")


# Class dict -> Encoded data str (JSON), Encoded data str -> dict
class Message():
    def __init__(self, values):
        try:
            self.originalData = self.__Dictmethod(values)
            self.encodedData = self.__JSONmethod(values)
        except ValueError:
            raise InvalidMessage()
        
    def __JSONmethod(self, values):
        if (isinstance(values, str)):
            return values
        elif (isinstance(values, dict)):
            return self.__DicttoJSON(values)
        else:
            raise InvalidMessage()
        
    def __Dictmethod(self, values):
        if (isinstance(values, dict)):
            return values
        elif (isinstance(values, str)):
            return self.__JSONtoDict(values)
        else:
            raise InvalidMessage()

    def __JSONtoDict(self, JSONstring):
        return json.loads(JSONstring)
    
    def __DicttoJSON(self, dictionary):
        return json.dumps(dictionary)



# Può essere utile avere uno strumento di log
class Peer():
    LOG_FILE_NAME = "peer.log"
    BUFFER_SIZE = 2048
    CLOSED_CONNECTION_REQUEST = "$$$EXIT"
    NEW_CONNECTION_REQUEST = "$$$NEWCONNECT"
    SELF_IP_ADDRESS = "127.0.0.1"
    MAX_NUMBER_LISTENER = 100

    def __init__(self, ip: str, port: int, peers = None, log: bool = False):
        self.__thread = []
        self.__observer = []
        self.__logger = log
        self.port = port
        self.username = None
        self.__connections = {}
        self.ip = ip

        self.__startLogger()

        try:
            self.ip, _ = obtainIpaddressFromString(self.ip)
            if self.ip not in list(local_ips()):
                self.__logError("Ip in args is not compatible")
                sys.exit(1)
        except (InvalidIpAddress):
            self.__logError("There is no ip in args")
            sys.exit(1)
        
        self.__set_peers(peers)
        self.__logger.info("Peers: " + str(self.peers))

    def start(self):        
        self.server_thread = threading.Thread(target=self.__serverStart, args=([self.port]))
        self.server_thread.daemon = True
        self.server_thread.start()
        self.__connectToAllPeers()

    def inputUsername(self, name: str):
        self.username = name

    def sendToEveryone(self, message: str):
        for (ip, port), _ in self.__connections.items():
            self.send(ip, port, message)
            
    def send(self, ip: str, port: int, message: str):
        #try:
            self.__connections[(ip, port)].sendall(bytes(message, 'utf-8'))
            self.__logInfo("Send message <" + message + "> to " + ip + ":" + str(port))
        #except Exception as e:
        #    self.__logError("Error send message: " + str(e.__dict__))

    def receive(self, conn):
        while True:
            message = conn.recv(self.BUFFER_SIZE).decode('utf-8')
            if (len(message) > 0):
                self.__logInfo("Received message <" + message + "> from ip: " 
                            + str(conn.getpeername()[0]) + " port: " + str(conn.getpeername()[1]))
                m = Message(message)
                self.notify(m)
                if(self.__isCloseConnectionMessage(m.originalData["message"])):
                    self.__logInfo("Closed connection with: " + m.originalData["serverIP"] + ":" +str(m.originalData["serverPort"]))
                    self.disconnect(m.originalData["serverIP"], m.originalData["serverPort"])
                    return
                if(self.__isNewConnectionMessage(m)):
                    self.__acceptNewConnection(m)
            
    def addObserver(self, observer):
        self.__observer.append(observer)

    def notify(self, message):
        for singleObserver in self.__observer:
            singleObserver.handleOutputMessage(message)

    def connect(self, ip: str, port: int):
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client.connect((ip, port))
            self.__connections[(ip, port)] = client
            self.send(ip, port, Message(self.__newConnectionMessage()).encodedData)
            self.__logInfo("Connected with ip: " + ip + " port: " + str(port))
            
        except OSError:
            self.__logError("Can not connect with ip: " + ip + " port: " + str(port))
            data = {
                "username": "TCP Group Chat",
                "message": "Impossible to connect with ip: " + ip + " port: " + str(port)
            }
            self.notify(Message(data))
            #del self.__connections[(ip, port)]

            #raise ImpossibleToConnectToPeer("Impossible to connect with ip: " + ip + " port: " + str(port))
                    
    def disconnect(self, ip: str, port: int):
        self.__connections[(ip, port)].close()
        del self.__connections[(ip, port)]

    def close(self):
        for (ip, port), value in self.__connections.items():
            self.send(ip, port, Message(self.__disconnectionMessage()).encodedData)
            self.__connections[(ip, port)].close()
            self.__logInfo("Closed connection with: " + ip + ":" +str(port))
        if self.__socket:
            self.__socket.close()
        #for i in self.__thread:
        #    i.join()
        #self.server_thread.join()

    def __connectToAllPeers(self):
        for addr, port in self.peers:
            #try:
                addr, port = obtainIpaddressFromString(addr, port)
                self.connect(addr, port)
            #except ImpossibleToConnectToPeer:
            #    del self.peers[(addr, port)]

    def __newConnectionMessage(self):
        return {
            "serverIP": self.ip,
            "serverPort": self.port,
            "username": self.username if self.__isUsernameSet() 
                else (self.ip + ":" + str(self.port)),
            "message": self.NEW_CONNECTION_REQUEST
        }
    
    def __disconnectionMessage(self):
        return {
            "serverIP": self.ip,
            "serverPort": self.port,
            "username": self.username if self.__isUsernameSet() 
                else (self.ip + ":" + str(self.port)),
            "message": self.CLOSED_CONNECTION_REQUEST
        }

    def __acceptNewConnection(self, message: Message):
        ip, port = obtainIpaddressFromString(message.originalData["serverIP"], 
                                               port = message.originalData["serverPort"])
        self.connect(ip, port)

    def __isNewConnectionMessage(self, message: Message):
        return message.originalData["message"] == self.NEW_CONNECTION_REQUEST and not ((message.originalData["serverIP"], message.originalData["serverPort"]) in self.__connections)

    def __isCloseConnectionMessage(self, message):
        return message == self.CLOSED_CONNECTION_REQUEST

    def __serverStart(self, port):
        try:
            self.server_thread = threading.Thread(target=self.__set_server, args=([port]))
            self.server_thread.daemon = True
            self.server_thread.start()
            self.server_thread.join()
        except KeyboardInterrupt:
            for thread in self.__thread:
                thread.join()
            self.close()
            self.__logInfo("Server socket closed")
            sys.exit(0)

    def __set_server(self, port):
        self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.__socket.bind(obtainIpaddressFromString(self.SELF_IP_ADDRESS, port=port))
        except (InvalidPortRange, InvalidIpAddress) as e:
            self.__logError(e)
            sys.exit(1)
        self.__socket.listen(self.MAX_NUMBER_LISTENER)
        while True:
            conn, _ = self.__socket.accept()  # Accept a client connection
            thread = threading.Thread(target=self.receive, args=([conn]))
            thread.daemon = True
            self.__thread.append(thread)
            thread.start()  # Start a new thread for each client
            self.__logInfo("New connection active from ip: " + str(conn.getpeername()[0]) + " port: " + str(conn.getpeername()[1]))

    def __set_peers(self, peers):
        if peers is None:
            peers = set()
        try:
            self.peers = {obtainIpaddressFromString(peer) for peer in peers}
        except (InvalidPortRange, InvalidIpAddress) as e:
            self.__logError(e)
            sys.exit(1)

    def __logError(self, message):
        if (self.__logger):
                self.__logger.error((str(self.port) if not self.__isUsernameSet() 
                                else "{"+self.username+"} ") + message)
                
    def __logInfo(self, message):
        if (self.__logger):
                self.__logger.info((str(self.port) if not self.__isUsernameSet() 
                                else "{"+self.username+"} ") + message)
                
    def __isUsernameSet(self):
        if (self.username == None):
            return False
        else:
            return True
        
    def __startLogger(self):
        if (self.__logger):
            logging.basicConfig(filename=(self.ip+":"+str(self.port)+".log"),
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    filemode='w')
            self.__logger = logging.getLogger()
            self.__logger.setLevel(logging.DEBUG)
    
    # funzione privata periodica di controllo della rete


class Controller():
    def __init__(self, args):
        self.__observer = []
        self.__peer = Peer(args[1], int(args[2]), peers=args[3:], log=True)
        self.__peer.addObserver(self)
        self.addObserver(self.__peer)
        
        self.___inputUsername()
        print('\nType your message and press Enter to send it. Messages from other peers will be displayed below.\n')

        time.sleep(1)
        self.__peer.start()
        
    def start(self):
        try:
            while True:
                content = input()
                data = {
                    "username": self.__username,
                    "message": content
                }
                self.handleInputMessage(Message(data))
        except KeyboardInterrupt:
            self.__peer.close()

    def addObserver(self, observer):
        self.__observer.append(observer)

    def handleOutputMessage(self, message: Message):
        if (message.originalData["message"] == self.__peer.NEW_CONNECTION_REQUEST):
            print("<" + message.originalData["username"] + ">: Join the chat")
        elif (message.originalData["message"] == self.__peer.CLOSED_CONNECTION_REQUEST):
            print("<" + message.originalData["username"] + ">: Left the chat")
        else:
            print("<" + message.originalData["username"] + ">: " + message.originalData["message"])

    def handleInputMessage(self, message: Message):
        for singlebserver in self.__observer:
            singlebserver.sendToEveryone(message.encodedData)

    def ___inputUsername(self):
        print("\nEnter your username to start the chat: ")
        self.__username = input()
        self.__peer.inputUsername(self.__username)
        

class View():
    def outputMessage(self, message: str):
        pass
    def inputMessage(self) -> str:
        pass

# TODO creare test peer
# TODO sistemare Exception
# TODO refactoring codice
# TODO gestire problemi e stabilità connessione (network partition...)
# TODO ordinare codice
# TODO controllare se tutti i thread sono necessari
# TODO associare connessioni con thread
# TODO controllare concorrenza

if __name__=='__main__':
    c = Controller(sys.argv)
    c.start()


class Test():
    # Those test check ip address and port
    # Valid "x.x.x.x:port" format
    @given(indirizzo_ip=st.ip_addresses(v=4),
           porta=st.integers(min_value=1, max_value=65535))
    def test_IpAddressValidFormat(self, indirizzo_ip, porta):
        assert obtainIpaddressFromString(str(indirizzo_ip)+ ":" + str(porta))
    
    # Invalid port values
    @given(indirizzo_ip=st.ip_addresses(v=4),
           porta=st.integers(min_value=65536, max_value=6553555))
    def test_IpAddressInvalidPortValue1(self, indirizzo_ip, porta):
        with pytest.raises(InvalidPortRange):
            obtainIpaddressFromString(str(indirizzo_ip)+ ":" + str(porta))
    
    @given(indirizzo_ip=st.ip_addresses(v=4),
           porta=st.integers(min_value=-1235431, max_value=-1))
    def test_IpAddressInvalidPortValue2(self, indirizzo_ip, porta):
        with pytest.raises(InvalidPortRange):
            obtainIpaddressFromString(str(indirizzo_ip)+ ":" + str(porta))

    # Invalid IPv6 address 
    @given(indirizzo_ip=st.ip_addresses(v=6),
           porta=st.integers(min_value=1, max_value=65535))
    def test_IpAddressInvalidIPv6(self, indirizzo_ip, porta):
        with pytest.raises(InvalidIpAddress):
            obtainIpaddressFromString(str(indirizzo_ip)+ ":" + str(porta))
    
    # Invalid ip address
    @given(indirizzo_ip=st.text(),
           porta=st.integers(min_value=1, max_value=65535))
    def test_IpAddressInvalidAddress(self, indirizzo_ip, porta):
        with pytest.raises(InvalidIpAddress):
            obtainIpaddressFromString(str(indirizzo_ip)+ ":" + str(porta))

    # Valid ip address without port
    @given(indirizzo_ip=st.ip_addresses(v=4))
    def test_IpAddressValidAddressWoutPort(self, indirizzo_ip):
        assert obtainIpaddressFromString(str(indirizzo_ip))

    # Invalid ip address without port
    @given(indirizzo_ip=st.ip_addresses(v=6))
    def test_IpAddressInvalidAddressWoutPort(self, indirizzo_ip):
        with pytest.raises(InvalidIpAddress):
            obtainIpaddressFromString(str(indirizzo_ip))

    # Invalid port, because is not an integer
    @given(indirizzo_ip=st.ip_addresses(v=4),
           porta=st.text(alphabet=string.ascii_letters + string.punctuation))
    def test_IpAddressInvalidPortNotInteger(self, indirizzo_ip, porta):
        with pytest.raises(InvalidIpAddress):
            obtainIpaddressFromString(str(indirizzo_ip)+ ":" + str(porta))

    # Test localhost string
    def test_IpAddressValidLocalhost(self):
        assert obtainIpaddressFromString('localhost:8080')


    # Valid Message from dict
    @given(nome1 = st.text(alphabet=string.ascii_letters + string.punctuation),
           nome2 = st.text(alphabet=string.ascii_letters + string.punctuation),
           valore1 = st.text(),
           valore2 = st.text())
    def test_MessageValidFromDict(self, nome1, nome2, valore1, valore2):
        testDict = {nome1: valore1, nome2: valore2}
        ms = Message(testDict)
        assert ms.originalData == testDict
        assert isinstance(ms.originalData, dict)

    # None args
    def test_MessageInvalidNoneArgs(self):
        with pytest.raises(InvalidMessage):
            assert Message(None)

    # Invalid Type Args
    def test_MessageInvalidListArgs(self):
        with pytest.raises(InvalidMessage):
            assert Message(list())

    # Valid Message from json
    @given(nome1 = st.text(alphabet=string.ascii_letters + string.punctuation),
           nome2 = st.text(alphabet=string.ascii_letters + string.punctuation),
           valore1 = st.text(),
           valore2 = st.text())
    def test_MessageValidFromJSON(self, nome1, nome2, valore1, valore2):
        testDict = {nome1: valore1, nome2: valore2}
        jsonString = json.dumps(testDict)
        ms = Message(jsonString)
        assert ms.encodedData == jsonString
        assert isinstance(ms.encodedData, str)

    @given(valore = st.text(alphabet=string.ascii_letters + string.punctuation))
    def test_MessageInvalidString(self, valore):
        with pytest.raises(InvalidMessage):
            assert Message(valore)
