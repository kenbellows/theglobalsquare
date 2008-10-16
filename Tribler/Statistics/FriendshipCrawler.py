# see LICENSE.txt for license information

from Tribler.Core.CacheDB.SqliteCacheDBHandler import SQLiteCacheDB

class FriendshipCrawler:
    __single = None

    @classmethod
    def get_instance(cls, *args, **kargs):
        if not cls.__single:
            cls.__single = cls(*args, **kargs)
        return cls.__single

    def __init__(self):
        self._sqlite_cache_db = SQLiteCacheDB.getInstance()

    def query_initiator(self, permid, selversion, request_callback):
        """
        Established a new connection. Send a CRAWLER_DATABASE_QUERY request.
        @param permid The Tribler peer permid
        @param selversion The oberlay protocol version
        @param request_callback Call this function one or more times to send the requests: request_callback(message_id, payload)
        """
        if DEBUG: 
            print >>sys.stderr, "crawler: SeedingStatsDB_query_initiator"
        return request_callback(CRAWLER_FRIENDSHIP_STATS, "SELECT * FROM SeedingStats WHERE crawled = 0")

    def handle_crawler_request(self, permid, selversion, channel_id, message, reply_callback):
        """
        Received a CRAWLER_DATABASE_QUERY request.
        @param permid The Crawler permid
        @param selversion The overlay protocol version
        @param channel_id Identifies a CRAWLER_REQUEST/CRAWLER_REPLY pair
        @param message The message payload
        @param reply_callback Call this function once to send the reply: reply_callback(payload [, error=123])
        """
        if DEBUG:
            print >> sys.stderr, "crawler: handle_friendship_crawler_database_query_request", message

        # execute the sql
        try:
            cursor = self._sqlite_cache_db.execute_read(message)

        except Exception, e:
            reply_callback(str(e), 1)
        else:
            if cursor:
                reply_callback(cPickle.dumps(list(cursor), 2))
            else:
                reply_callback("error", 1)

        return True

    def handle_crawler_reply(self, permid, selversion, channel_id, message, request_callback):
        """
        Received a CRAWLER_FRIENDSHIP_STATS request.
        @param permid The Crawler permid
        @param selversion The overlay protocol version
        @param channel_id Identifies a CRAWLER_REQUEST/CRAWLER_REPLY pair
        @param message The message payload
        @param request_callback Call this function one or more times to send the requests: request_callback(message_id, payload)
        """
        if DEBUG:
            print >> sys.stderr, "crawler: handle_friendship_crawler_database_query_reply"
            print >> sys.stderr, "crawler:", cPickle.loads(message)

        return True 

