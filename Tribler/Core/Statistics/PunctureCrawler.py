# Written by Gertjan Halkes
# see LICENSE.txt for license information

# Crawler and logging module for UDPPuncture testing

from Tribler.Core.Session import Session
from Tribler.Core.Statistics.Crawler import Crawler
from Tribler.Core.BitTornado.BT1.MessageID import CRAWLER_PUNCTURE_QUERY
from Tribler.Core.Utilities.utilities import show_permid, show_permid_short
import os
import time
import sys
import zlib
import thread

DEBUG = False

def get_reporter_instance():
    return SimpleFileReporter.get_instance()

class SimpleFileReporter:
    __single = None
    lock = thread.allocate_lock()

    @classmethod
    def get_instance(cls, *args, **kw):
        cls.lock.acquire()
        try:
            if not cls.__single:
                cls.__single = cls()
        finally:
            cls.lock.release()
        return cls.__single
    
    def __init__(self):
        self.file = None
        self.path = os.path.join(Session.get_default_state_dir(), "udppuncture.log")

    def add_event(self, ignore, msg):
        SimpleFileReporter.lock.acquire()
        try:
            try:
                if not self.file:
                    self.file = open(self.path, 'a+b')
                self.file.write('%.2f %s\n' %(time.time(), msg))
                self.file.flush()
            except:
                if DEBUG:
                    print >>sys.stderr, 'Error writing puncture log'
        finally:
            SimpleFileReporter.lock.release()

class PunctureCrawler:
    __single = None

    @classmethod
    def get_instance(cls, *args, **kargs):
        if not cls.__single:
            cls.__single = cls(*args, **kargs)
        return cls.__single

    def __init__(self):
        crawler = Crawler.get_instance()
        if crawler.am_crawler():
            self._file = open("puncturecrawler.txt", "a")
            self._file.write("# Crawler started at %.2f\n" % time.time())
            self._file.flush()
            self._repexlog = None
        else:
            self.reporter = get_reporter_instance()

    def query_initiator(self, permid, selversion, request_callback):
        """
        Established a new connection. Send a CRAWLER_PUNCTURE_QUERY request.
        @param permid The Tribler peer permid
        @param selversion The overlay protocol version
        @param request_callback Call this function one or more times to send the requests: request_callback(message_id, payload)
        """
        request_callback(CRAWLER_PUNCTURE_QUERY, '', callback=self._after_request_callback)

    def _after_request_callback(self, exc, permid):
        """
        Called by the Crawler with the result of the request_callback
        call in the query_initiator method.
        """
        if not exc:
            if DEBUG: print >>sys.stderr, "puncturecrawler: request sent to", show_permid_short(permid)
            self._file.write("REQUEST %s %.2f\n" % (show_permid(permid), time.time()))
            self._file.flush()

    def handle_crawler_request(self, permid, selversion, channel_id, message, reply_callback):
        """
        Received a CRAWLER_UDPUNCTURE_QUERY request.
        @param permid The Crawler permid
        @param selversion The overlay protocol version
        @param channel_id Identifies a CRAWLER_REQUEST/CRAWLER_REPLY pair
        @param message The message payload
        @param reply_callback Call this function once to send the reply: reply_callback(payload [, error=123])
        """
        if DEBUG:
            print >> sys.stderr, "puncturecrawler: handle_crawler_request", show_permid_short(permid), message

        SimpleFileReporter.lock.acquire()
        try:
            # retrieve puncture history
            file = self.reporter.file
            try:
                file.close()
                self.reporter.file = None
                os.rename(self.reporter.path, self.reporter.path + '.crawl')
                file = open(self.reporter.path + '.crawl', 'r')
                result = ("%.2f CRAWL\n" % time.time()) + file.read()
                result = zlib.compress(result)
                reply_callback(result)
            except Exception, e:
                reply_callback(str(e), error=1)
            file.close()
            os.remove(self.reporter.path + '.crawl')
        finally:
            SimpleFileReporter.lock.release()

    def handle_crawler_reply(self, permid, selversion, channel_id, channel_data, error, message, request_callback):
        """
        Received a CRAWLER_UDPUNCTURE_QUERY reply.
        @param permid The Crawler permid
        @param selversion The overlay protocol version
        @param channel_id Identifies a CRAWLER_REQUEST/CRAWLER_REPLY pair
        @param error The error value. 0 indicates success.
        @param message The message payload
        @param request_callback Call this function one or more times to send the requests: request_callback(message_id, payload)
        """
        try:
            if error:
                if DEBUG:
                    print >> sys.stderr, "puncturecrawler: handle_crawler_reply", error, message

                self._file.write("ERROR %s %.2f %d %s\n" % (show_permid(permid), time.time(), error, message))
                self._file.flush()

            else:
                if DEBUG:
                    print >> sys.stderr, "puncturecrawler: handle_crawler_reply", show_permid_short(permid)
                
                self._file.write("REPLY %s %.2f\n" % (show_permid(permid), time.time()))
                self._file.write(zlib.decompress(message))
                self._file.flush()
        except:
            if DEBUG:
                print >>sys.stderr, "puncturecrawler: error writing to file"
