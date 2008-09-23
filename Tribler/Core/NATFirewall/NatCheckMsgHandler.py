from threading import Thread, Lock
from traceback import print_exc
import socket
import sys

from Tribler.Core.BitTornado.BT1.MessageID import *
from Tribler.Core.BitTornado.bencode import bencode, bdecode
from Tribler.Core.NATFirewall.NatCheck import GetNATType
from Tribler.Core.NATFirewall.TimeoutCheck import timeout_check
from Tribler.Core.Overlay.OverlayThreadingBridge import OverlayThreadingBridge
from Tribler.Core.Overlay.SecureOverlay import OLPROTO_VER_SEVENTH
from Tribler.Core.Utilities.utilities import show_permid_short
from Tribler.Core.simpledefs import *

DEBUG = True

class NatCheckMsgHandler:

    __single = None

    def __init__(self):
        if NatCheckMsgHandler.__single:
            raise RuntimeError, "NatCheckMsgHandler is singleton"
        NatCheckMsgHandler.__single = self

    @staticmethod
    def getInstance(*args, **kw):
        if NatCheckMsgHandler.__single is None:
            NatCheckMsgHandler(*args, **kw)
        return NatCheckMsgHandler.__single

    def register(self, overlay_bridge, launchmany):
        if DEBUG:
            print >> sys.stderr, "NatCheckMsgHandler: register"
        self.overlay_bridge = overlay_bridge
        self.session = launchmany.session		 
        self.superpeer_db = launchmany.superpeer_db 
        self.doNatCheckSender = None
        self.natcheck_reply = ""
        self.peerlist = None
        self.registered = True

    def handleMessage(self, permid, selversion, message):
        if not self.registered:
            if DEBUG:
                print >> sys.stderr, "NatCheckMsgHandler: handleMessage got message, but we're not enabled"
            return False

        if len(message) > 0 and message[0] == DO_NAT_CHECK:
            if DEBUG:
                print >> sys.stderr, "NatCheckMsgHandler: received DO_NAT_CHECK message"
            return self.gotDoNatCheckMessage(message, permid, selversion)

    def gotDoNatCheckMessage(self, recv_msg, sender_permid, selversion):
        if len(recv_msg) is not 1:
            raise RuntimeError, "NatCheckMsgHandler: bad DO_NAT_CHECK message"

        superpeers = self.superpeer_db.getSuperPeers()
        if sender_permid in superpeers: # NAT check started only if requested by a superpeer
            self.doNatCheckSender = sender_permid
            if DEBUG:
                print >> sys.stderr,"NatCheckMsgHandler: DO_NAT_CHECK sender is superpeer"

            try:
                if DEBUG:
                    print >>sys.stderr,"NatCheckMsgHandler: start_nat_type_detect()"
                nat_check_client = NatCheckClient.getInstance(self.session)
                nat_check_client.try_start()
            except:
                print_exc()
        elif DEBUG:
            print >>sys.stderr, "NatCheckMsgHandler: a nat-check-request is only allowed by a superpeer"

    def natthreadcb_natCheckReplyCallback(self, ncr_data):
        if DEBUG:
            print >> sys.stderr, "NAT type: ", ncr_data

        # connect to the peer who has made the NAT_CHECK request
        if self.doNatCheckSender is not None:
            try:
                ncr_msg = bencode(ncr_data)
            except:
                print_exc()
                if DEBUG: print >> sys.stderr, "error ncr_data:", ncr_data
                return False
            self.natcheck_reply = ncr_msg
            if DEBUG:
                print >> sys.stderr, "NatCheckMsgHandler:", ncr_data
            self.overlay_bridge.connect(self.doNatCheckSender, self.natCheckReplyConnectCallback)

    def validDoNatCheckMessage(self, ncr_data):
        return True

    # send the message
    def natCheckReplyConnectCallback(self, exc, dns, permid, server):
        if DEBUG:
            print >> sys.stderr, "******* NAT_CHECK_REPLY: connecting to", show_permid_short(permid), exc
        if exc is not None:
            if DEBUG:
                print >> sys.stderr, "********* NAT_CHECK_REPLY: not able to connect to", show_permid_short(permid), exc
            return False
        self.overlay_bridge.send(self.doNatCheckSender, NAT_CHECK_REPLY+self.natcheck_reply, self.natCheckReplySendCallback)
        return True

    def natCheckReplySendCallback(self, exc, permid):
        if DEBUG:
            print >> sys.stderr, "******* NAT_CHECK_REPLY was sent to", show_permid_short(permid), exc
        if exc is not None:
            return False
        return True

class NatCheckClient(Thread):

    __single = None

    def __init__(self, session):
        Thread.__init__(self)
        if NatCheckClient.__single:
            raise RuntimeError, "NatCheckClient is singleton"
        NatCheckClient.__single = self

        self.setName("NatCheckClient")
        self.setDaemon(True)
        self.lock = Lock()
        self.session = session
        self.permid = self.session.get_permid()
        self.nat_type = None
        self.nat_timeout = -1
        self._nat_callbacks = [] # list with callback functions that want to know the nat_type

    @staticmethod
    def getInstance(*args, **kw):
        if NatCheckClient.__single is None:
            NatCheckClient(*args, **kw)
        return NatCheckClient.__single

    def try_start(self):		
        self.lock.acquire()
        try:
            if not self.isAlive():
               	self.start()
                while not self.isAlive():
                    time.sleep(0)
        finally:
            self.lock.release()

    def run(self):
        self.nat_discovery()

    def timeout_check(self, pingback):
        """
        Find out NAT timeout
        """
        return timeout_check(self.permid, pingback)

    def natcheck(self, udpsock, privateIP, privatePort, server1, server2):
        """
        Find out NAT type and public address and port
        """        
        NatType, publicIP, publicPort = GetNATType(udpsock, privateIP, privatePort, server1, server2)
        if DEBUG: print >> sys.stderr, "NATCheck:", "NAT Type: " + NatType[1]
        if DEBUG: print >> sys.stderr, "NATCheck:", "Public Address: " + publicIP + ":" + str(publicPort)
        if DEBUG: print >> sys.stderr, "NATCheck:", "Private Address: " + privateIP + ":" + str(privatePort)
        return NatType, publicIP, publicPort, privateIP, privatePort

    def register(self, request, tcpsock):
        """
        Register connection information
        """
        BUFSIZ = 1024
        reply = ""

        try:
            tcpsock.send(request)
        except error, (errno, strerror):
            if DEBUG: print >> sys.stderr, "NATCheck:", strerror

        tcpsock.settimeout(10)

        try:
            reply = tcpsock.recv(BUFSIZ)

        except timeout:
            if DEBUG: print >> sys.stderr, "NATCheck:", "Connection to the coordinator has timed out"

        except socket.error, (errno, strerror):
            if DEBUG: print >> sys.stderr, "NATCheck:", "Connection error with the coordinator: %s (%s)" % (strerror, str(errno))

            if tcpsock:
                tcpsock.close()

        return reply

    def get_nat_type(self, callback=None):
        """
        When a callback parameter is supplied it will always be
        called. When the NAT-type is already known the callback will
        be made instantly. Otherwise, the callback will be made when
        the NAT discovery has finished.
        """
        if self.nat_type:
            if callback:
                callback(self.nat_type)
            return self.nat_type
        else:
            if callback:
                self._nat_callbacks.append(callback)
            self.try_start()
            return "Unknown NAT/Firewall"

    def _perform_nat_type_notification(self):
        nat_type = self.get_nat_type()
        callbacks = self._nat_callbacks
        self._nat_callbacks = []

        for callback in callbacks:
            try:
                callback(nat_type)
            except:
                pass

    def nat_discovery(self):
        """
        Main method of the class: launches nat discovery algorithm
        """
        privatePort = self.session.get_puncturing_private_port()
        stun_servers = self.session.get_stun_servers()
        stun1 = stun_servers[0]
        stun2 = stun_servers[1]
        pingback_servers = self.session.get_pingback_servers()
        pingback = pingback_servers[0]
        coordinators = self.session.get_puncturing_coordinators()
        coordinator = coordinators[0]

        if DEBUG: print >> sys.stderr, "NATCheck:", 'Starting natcheck client with %s %s %s %s %s' % (privatePort, stun1, stun2, pingback, coordinator)

        # Set up the sockets
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('www.tribler.org',80))
        privateIP = s.getsockname()[0]
        del s

        privateAddr = (privateIP, privatePort)

        # TCP socket
        tcpsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        bind = 0
        while bind == 0:
            privateAddr = (privateIP, privatePort)
            if DEBUG: print >> sys.stderr, "NATCheck:", "binding address: " + str(privateAddr)

            try:
                tcpsock.bind(privateAddr)
                bind = 1
            except socket.error, (errno, strerror):
                privatePort += 1
                bind = 0

                if tcpsock :
                    tcpsock.close()
                    tcpsock = False
                    tcpsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if DEBUG: print >> sys.stderr, "NATCheck:", "Could not open socket: %s" % (strerror)

        tcpsock.settimeout(30)

        try:
            tcpsock.connect(coordinator)
        except timeout:
            if tcpsock:
                tcpsock.close()
                tcpsock = False
            if DEBUG: print >> sys.stderr, "NATCheck:", "Connection to the coordinator has timed out"
        except socket.error, (errno, strerror):
            if tcpsock:
                tcpsock.close()
                tcpsock = False
            if DEBUG: print >> sys.stderr, "NATCheck:", "Could not connect socket: %s" % (strerror)

        # UDP socket
        udpsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udpsock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)

        try:
            udpsock.bind(privateAddr)
        except socket.error, (errno, strerror):
            if udpsock:
                udpsock.close()
                udpsock = False
            if DEBUG: print >> sys.stderr, "NATCheck:", "Could not open socket: %s" % (strerror)

        performed_nat_type_notification = False
        if udpsock:
            udpsock.settimeout(5)

            # Check what kind of NAT the peer is behind
            NatType, publicIP, publicPort, privateIP, privatePort = self.natcheck(udpsock, privateIP, privatePort, stun1, stun2)
            self.nat_type = NatType[1]

            # notify any callbacks. We need to do this before the
            # timeout_check, otherwise we may end up waiting for a
            # long long time
            self._perform_nat_type_notification()
            performed_nat_type_notification = True

            udpsock.close()

            if tcpsock:
                tcpsock.close()

            # Check the UDP timeout of the NAT the peer is behind
            if NatType[0] != 0:
                self.nat_timeout = self.timeout_check(pingback)
                if DEBUG: print >> sys.stderr, "NATCheck:", str("Nat UDP timeout is: " + str(self.nat_timeout))

            self.nat_params = [NatType[1], NatType[0], self.nat_timeout, publicIP, int(publicPort), privateIP, privatePort]
            if DEBUG: print >> sys.stderr, "NATCheck:", str(self.nat_params)

            NatCheckMsgHandler.getInstance().natthreadcb_natCheckReplyCallback(self.nat_params)

        if not performed_nat_type_notification:
            self._perform_nat_type_notification()