# Written by Bram Cohen
# see LICENSE.txt for license information

import socket
import errno
try:
    from select import poll, POLLIN, POLLOUT, POLLERR, POLLHUP
    timemult = 1000
except ImportError:
    from selectpoll import poll, POLLIN, POLLOUT, POLLERR, POLLHUP
    timemult = 1
from time import sleep
from clock import clock
import sys
from random import shuffle, randrange
from traceback import print_exc

from threading import currentThread

# from BT1.StreamCheck import StreamCheck
# import inspect
try:
    True
except:
    True = 1
    False = 0

DEBUG = True

all = POLLIN | POLLOUT

if sys.platform == 'win32':
    SOCKET_BLOCK_ERRORCODE=10035    # WSAEWOULDBLOCK
else:
    SOCKET_BLOCK_ERRORCODE=errno.EWOULDBLOCK


class SingleSocket:
    """ 
    There are two places to create SingleSocket:
    incoming connection -- SocketHandler.handle_events
    outgoing connection -- SocketHandler.start_connection_raw
    """
    
    def __init__(self, socket_handler, sock, handler, ip = None):
        self.socket_handler = socket_handler
        self.socket = sock
        self.handler = handler
        self.buffer = []
        self.last_hit = clock()
        self.fileno = sock.fileno()
        self.connected = False
        self.skipped = 0
#        self.check = StreamCheck()
        self.myip = None
        self.myport = -1
        self.ip = None
        self.port = -1
        try:
            (self.myip,self.myport) = self.socket.getsockname()
            (self.ip,self.port) = self.socket.getpeername()
        except:
            if ip is None:
                self.ip = 'unknown'
            else:
                self.ip = ip
        
    def get_ip(self, real=False):
        if real:
            try:
                (self.ip,self.port) = self.socket.getpeername()
            except:
                pass
        return self.ip
    
    def get_port(self, real=False):
        if real:
            self.get_ip(True)
        return self.port

    def get_myip(self, real=False):
        if real:
            try:
                (self.myip,self.myport) = self.socket.getsockname()
            except:
                pass
        return self.myip
    
    def get_myport(self, real=False):
        if real:
            self.get_myip(True)
        return self.myport
        
    def close(self):
        '''
        for x in xrange(5,0,-1):
            try:
                f = inspect.currentframe(x).f_code
                print (f.co_filename,f.co_firstlineno,f.co_name)
                del f
            except:
                pass
        print ''
        '''
        assert self.socket
        self.connected = False
        sock = self.socket
        self.socket = None
        self.buffer = []
        del self.socket_handler.single_sockets[self.fileno]
        self.socket_handler.poll.unregister(sock)
        sock.close()

    def shutdown(self, val):
        self.socket.shutdown(val)

    def is_flushed(self):
        return not self.buffer

    def write(self, s):
#        self.check.write(s)
        # Arno: fishy concurrency problem, sometimes self.socket is None
        if self.socket is None:
            return
        #assert self.socket is not None
        self.buffer.append(s)
        if len(self.buffer) == 1:
            self.try_write()

    def try_write(self):
        
        if self.connected:
            dead = False
            try:
                while self.buffer:
                    buf = self.buffer[0]
                    amount = self.socket.send(buf)
                    if amount == 0:
                        self.skipped += 1
                        break
                    self.skipped = 0
                    if amount != len(buf):
                        self.buffer[0] = buf[amount:]
                        break
                    del self.buffer[0]
            except socket.error, e:
                #if DEBUG:
                #    print_exc(file=sys.stderr)
                blocked=False
                try:
                    blocked = (e[0] == SOCKET_BLOCK_ERRORCODE) 
                    dead = not blocked
                except:
                    dead = True
                if not blocked:
                    self.skipped += 1
            if self.skipped >= 5:
                dead = True
            if dead:
                self.socket_handler.dead_from_write.append(self)
                return
        if self.buffer:
            self.socket_handler.poll.register(self.socket, all)
        else:
            self.socket_handler.poll.register(self.socket, POLLIN)
        
    def set_handler(self, handler):    # can be: NewSocketHandler, Encoder, En_Connection
        self.handler = handler


class SocketHandler:
    def __init__(self, timeout, ipv6_enable, readsize = 100000):
        self.timeout = timeout
        self.ipv6_enable = ipv6_enable
        self.readsize = readsize
        self.poll = poll()
        # {socket: SingleSocket}
        self.single_sockets = {}
        self.dead_from_write = []
        self.max_connects = 1000
        self.servers = {}

    def scan_for_timeouts(self):
        t = clock() - self.timeout
        tokill = []
        for s in self.single_sockets.values():
            if s.last_hit < t:
                tokill.append(s)
        for k in tokill:
            if k.socket is not None:
                if DEBUG:
                    print >> sys.stderr,"SocketHandler: scan_timeout closing connection",k.get_ip()
                self._close_socket(k)

    def bind(self, port, bind = '', reuse = False, ipv6_socket_style = 1):
        port = int(port)
        addrinfos = []
        self.servers = {}
        self.interfaces = []
        # if bind != "" thread it as a comma seperated list and bind to all
        # addresses (can be ips or hostnames) else bind to default ipv6 and
        # ipv4 address
        if bind:
            if self.ipv6_enable:
                socktype = socket.AF_UNSPEC
            else:
                socktype = socket.AF_INET
            bind = bind.split(',')
            for addr in bind:
                if sys.version_info < (2, 2):
                    addrinfos.append((socket.AF_INET, None, None, None, (addr, port)))
                else:
                    addrinfos.extend(socket.getaddrinfo(addr, port,
                                               socktype, socket.SOCK_STREAM))
        else:
            if self.ipv6_enable:
                addrinfos.append([socket.AF_INET6, None, None, None, ('', port)])
            if not addrinfos or ipv6_socket_style != 0:
                addrinfos.append([socket.AF_INET, None, None, None, ('', port)])
        for addrinfo in addrinfos:
            try:
                server = socket.socket(addrinfo[0], socket.SOCK_STREAM)
                if reuse:
                    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.setblocking(0)
                if DEBUG:
                    print >> sys.stderr,"SocketHandler: Try to bind socket on", addrinfo[4], "..."
                server.bind(addrinfo[4])
                self.servers[server.fileno()] = server
                if bind:
                    self.interfaces.append(server.getsockname()[0])
                if DEBUG:
                    print >> sys.stderr,"SocketHandler: OK"
                server.listen(64)
                self.poll.register(server, POLLIN)
            except socket.error, e:
                for server in self.servers.values():
                    try:
                        server.close()
                    except:
                        pass
                if self.ipv6_enable and ipv6_socket_style == 0 and self.servers:
                    raise socket.error('blocked port (may require ipv6_binds_v4 to be set)')
                raise socket.error(str(e))
        if not self.servers:
            raise socket.error('unable to open server port')
        self.port = port

    def find_and_bind(self, first_try, minport, maxport, bind = '', reuse = False,
                      ipv6_socket_style = 1, randomizer = False):
        e = 'maxport less than minport - no ports to check'
        if maxport-minport < 50 or not randomizer:
            portrange = range(minport, maxport+1)
            if randomizer:
                shuffle(portrange)
                portrange = portrange[:20]  # check a maximum of 20 ports
        else:
            portrange = []
            while len(portrange) < 20:
                listen_port = randrange(minport, maxport+1)
                if not listen_port in portrange:
                    portrange.append(listen_port)
        if first_try != 0:    # try 22 first, because TU only opens port 22 for SSH...
            try:
                self.bind(first_try, bind, reuse = reuse, 
                               ipv6_socket_style = ipv6_socket_style)
                return first_try
            except socket.error, e:
                pass
        for listen_port in portrange:
            try:
                self.bind(listen_port, bind, reuse = reuse,
                               ipv6_socket_style = ipv6_socket_style)
                return listen_port
            except socket.error, e:
                pass
        raise socket.error(str(e))


    def set_handler(self, handler):
        self.handler = handler


    def start_connection_raw(self, dns, socktype = socket.AF_INET, handler = None):
        # handler = Encoder, self.handler = Multihandler
        if handler is None:
            handler = self.handler
        sock = socket.socket(socktype, socket.SOCK_STREAM)
        sock.setblocking(0)
        try:
            if DEBUG:
                print >>sys.stderr,"SocketHandler: Initiate connection to",dns,"with socket #",sock.fileno()
            # Arno,2007-01-23: http://docs.python.org/lib/socket-objects.html 
            # says that connect_ex returns an error code (and can still throw 
            # exceptions). The original code never checked the return code.
            #
            err = sock.connect_ex(dns)
            if DEBUG:
                if err == 0:
                    msg = 'No error'
                else:
                    msg = errno.errorcode[err]
                print >>sys.stderr,"SocketHandler: connect_ex on socket #",sock.fileno(),"returned",err,msg
            if err != 0:
                if sys.platform == 'win32' and err == 10035:
                    # Arno, 2007-02-23: win32 always returns WSAEWOULDBLOCK, whether 
                    # the connect is to a live peer or not. Win32's version 
                    # of EINPROGRESS
                    pass
                elif err == errno.EINPROGRESS: # or err == errno.EALREADY or err == errno.EWOULDBLOCK:
                    # [Stevens98] says that UNICES return EINPROGRESS when the connect
                    # does not immediately succeed, which is almost always the case. 
                    pass
                else:
                    raise socket.error((err,errno.errorcode[err]))
        except socket.error, e:
            if DEBUG:
                print >> sys.stderr,"SocketHandler: SocketError in connect_ex",str(e)
            raise
        except Exception, e:
            if DEBUG:
                print >> sys.stderr,"SocketHandler: Exception in connect_ex",str(e)      
            raise socket.error(str(e))
        self.poll.register(sock, POLLIN)
        s = SingleSocket(self, sock, handler, dns[0])    # create socket to connect the peers obtained from tracker
        self.single_sockets[sock.fileno()] = s
        #if DEBUG:
        #    print >> sys.stderr,"SocketHandler: Created Socket"
        return s


    def start_connection(self, dns, handler = None, randomize = False):
        if handler is None:
            handler = self.handler
        if sys.version_info < (2, 2):
            s = self.start_connection_raw(dns, socket.AF_INET, handler)
        else:
#            if self.ipv6_enable:
#                socktype = socket.AF_UNSPEC
#            else:
#                socktype = socket.AF_INET
            try:
                try:
                    # Jie: we attempt to use this socktype to connect ipv6 addresses.
                    socktype = socket.AF_UNSPEC
                    addrinfos = socket.getaddrinfo(dns[0], int(dns[1]),
                                                   socktype, socket.SOCK_STREAM)
                except:
                    socktype = socket.AF_INET
                    addrinfos = socket.getaddrinfo(dns[0], int(dns[1]),
                                                   socktype, socket.SOCK_STREAM)
            except socket.error, e:
                raise
            except Exception, e:
                raise socket.error(str(e))
            if randomize:
                shuffle(addrinfos)
            for addrinfo in addrinfos:
                try:
                    s = self.start_connection_raw(addrinfo[4], addrinfo[0], handler)
                    break
                except Exception,e:
                    pass
            else:
                raise socket.error('unable to connect')
        return s


    def _sleep(self):
        sleep(1)
        
    def handle_events(self, events):
        for sock, event in events:
            #print >>sys.stderr,"SocketHandler: event on sock#",sock
            s = self.servers.get(sock)    # socket.socket
            if s:
                if event & (POLLHUP | POLLERR) != 0:
                    if DEBUG:
                        print >> sys.stderr,"SocketHandler: Got event, close server socket"
                    self.poll.unregister(s)
                    s.close()
                    del self.servers[sock]
                elif len(self.single_sockets) < self.max_connects:
                    try:
                        newsock, addr = s.accept()
                        if DEBUG:
                            print >> sys.stderr,"SocketHandler: Got connection from",newsock.getpeername()
                        newsock.setblocking(0)
                        nss = SingleSocket(self, newsock, self.handler)    # create socket for incoming peers and tracker
                        self.single_sockets[newsock.fileno()] = nss
                        self.poll.register(newsock, POLLIN)
                        self.handler.external_connection_made(nss)
                    except socket.error,e:
                        if DEBUG:
                            print >> sys.stderr,"SocketHandler: SocketError while accepting new connection",str(e)
                        self._sleep()
# 2fastbt_
                else:
                    print >> sys.stderr,"SocketHandler: too many connects"
# _2fastbt
            else:
                s = self.single_sockets.get(sock)
                if not s:
                    continue
                if (event & (POLLHUP | POLLERR)):
                    if DEBUG:
                        print >> sys.stderr,"SocketHandler: Got event, connect socket got error"
                        print >> sys.stderr,"SocketHandler: Got event, connect socket got error",s.ip,s.port
                    self._close_socket(s)
                    continue
                if (event & POLLIN):
                    try:
                        s.last_hit = clock()
                        data = s.socket.recv(100000)
                        if not data:
                            if DEBUG:
                                print >> sys.stderr,"SocketHandler: no-data closing connection",s.get_ip(),s.get_port()
                            self._close_socket(s)
                        else:
                            #if DEBUG:
                            #    print >> sys.stderr,"SocketHandler: Got data",s.get_ip(),s.get_port(),"len",len(data)

                            # btlaunchmany: NewSocketHandler, btdownloadheadless: Encrypter.Connection
                            s.handler.data_came_in(s, data)
                    except socket.error, e:
                        if DEBUG:
                            print >> sys.stderr,"SocketHandler: Socket error",str(e)
                        code, msg = e
                        if code != SOCKET_BLOCK_ERRORCODE:
                            if DEBUG:
                                print >> sys.stderr,"SocketHandler: closing connection because not WOULDBLOCK",s.get_ip(),"error",code
                            self._close_socket(s)
                            continue
                if (event & POLLOUT) and s.socket and not s.is_flushed():
                    s.connected = True
                    s.try_write()
                    if s.is_flushed():
                        s.handler.connection_flushed(s)

    def close_dead(self):
        while self.dead_from_write:
            old = self.dead_from_write
            self.dead_from_write = []
            for s in old:
                if s.socket:
                    if DEBUG:
                        print >> sys.stderr,"SocketHandler: close_dead closing connection",s.get_ip()
                    self._close_socket(s)

    def _close_socket(self, s):
        if DEBUG:
            print >> sys.stderr,"SocketHandler: closing connection to ",s.get_ip()
        s.close()
        s.handler.connection_lost(s)

    def do_poll(self, t):
        r = self.poll.poll(t*timemult)
        if r is None:
            connects = len(self.single_sockets)
            to_close = int(connects*0.05)+1 # close 5% of sockets
            self.max_connects = connects-to_close
            closelist = self.single_sockets.values()
            shuffle(closelist)
            closelist = closelist[:to_close]
            for sock in closelist:
                if DEBUG:
                    print >> sys.stderr,"SocketHandler: do_poll closing connection",sock.get_ip()
                self._close_socket(sock)
            return []
        return r     

    def get_stats(self):
        return { 'interfaces': self.interfaces, 
                 'port': self.port }


    def shutdown(self):
        for ss in self.single_sockets.values():
            try:
                ss.close()
            except:
                pass
        for server in self.servers.values():
            try:
                server.close()
            except:
                pass

