# Written by Arno Bakker
# see LICENSE.txt for license information

# TODO: let one hit to SIMPLE+METADATA be P2PURL
import unittest
import os
import sys
import time
import tempfile
import shutil
from Tribler.Core.Utilities.Crypto import sha
from types import StringType, DictType, IntType
from M2Crypto import EC

from Tribler.Test.test_as_server import TestAsServer
from olconn import OLConnection
from Tribler.Core.API import *
from Tribler.Core.BitTornado.bencode import bencode,bdecode
from Tribler.Core.BitTornado.BT1.MessageID import *
from Tribler.Core.BuddyCast.moderationcast_util import validChannelCastMsg, validVoteCastMsg
from Tribler.Core.BuddyCast.channelcast import ChannelCastCore
from Tribler.Core.BuddyCast.buddycast import BuddyCastCore
from Tribler.Core.BuddyCast.votecast import VoteCastCore
from Tribler.Core.CacheDB.sqlitecachedb import str2bin,bin2str

DEBUG=True


class TestChannels(TestAsServer):
    """ 
    Testing QUERY message of Social Network extension V1
    """
    
    def setUpPreSession(self):
        """ override TestAsServer """
        TestAsServer.setUpPreSession(self)
        self.config.set_buddycast(True)
        BuddyCastCore.TESTASSERVER = True
        ChannelCastCore.TESTASSERVER = True
        VoteCastCore.TESTASSERVER = True
        self.config.set_start_recommender(True)
        self.config.set_bartercast(True) 
        self.config.set_remote_query(True)
        self.config.set_crawler(False)       
        self.config.set_torrent_collecting_dir(os.path.join(self.config_path, "tmp_torrent_collecting"))

        # Write superpeers.txt
        self.install_path = tempfile.mkdtemp()
        spdir = os.path.join(self.install_path, LIBRARYNAME, 'Core')
        os.makedirs(spdir)

        statsdir = os.path.join(self.install_path, LIBRARYNAME, 'Core', 'Statistics')
        os.makedirs(statsdir)
        
        superpeerfilename = os.path.join(spdir, 'superpeer.txt')
        print >> sys.stderr,"test: writing empty superpeers to",superpeerfilename
        f = open(superpeerfilename, "w")
        f.write('# Leeg')
        f.close()

        self.config.set_install_dir(self.install_path)
        
        srcfiles = []
        srcfiles.append(os.path.join(LIBRARYNAME,"schema_sdb_v4.sql"))
        for srcfile in srcfiles:
            sfn = os.path.join('..','..',srcfile)
            dfn = os.path.join(self.install_path,srcfile)
            print >>sys.stderr,"test: copying",sfn,dfn
            shutil.copyfile(sfn,dfn)



    def setUpPostSession(self):
        """ override TestAsServer """
        TestAsServer.setUpPostSession(self)

        self.mypermid = str(self.my_keypair.pub().get_der())
        self.hispermid = str(self.his_keypair.pub().get_der())

        
        self.torrent_db = self.session.open_dbhandler(NTFY_TORRENTS)
        self.channelcast_db = self.session.open_dbhandler(NTFY_CHANNELCAST)
        self.votecast_db = self.session.open_dbhandler(NTFY_VOTECAST)
        try:
            # Add some torrents belonging to own channel
            tdef1, self.bmetainfo1 = self.get_default_torrent('sumfilename1','Hallo S01E10')
            dbrec= self.torrent_db.addExternalTorrent(tdef1, extra_info={"filename":"sumfilename1"})
            self.infohash1 = tdef1.get_infohash()
            self.channelcast_db.addOwnTorrent(tdef1)
            
            tdef2, self.bmetainfo2 = self.get_default_torrent('sumfilename2','Hallo S02E01')
            dbrec = self.torrent_db.addExternalTorrent(tdef2, extra_info={"filename":"sumfilename2"})
            self.infohash2 = tdef2.get_infohash()
            self.torrenthash2 = sha(self.bmetainfo2).digest()
            self.channelcast_db.addOwnTorrent(tdef2)
    
            tdef3, self.bmetainfo3 = self.get_default_torrent('sumfilename3','Halo Demo')
            self.torrent_db.addExternalTorrent(tdef3, extra_info={"filename":"sumfilename3"})
            self.infohash3 = tdef3.get_infohash()
            self.torrenthash3 = sha(self.bmetainfo3).digest()
            self.channelcast_db.addOwnTorrent(tdef3)
            
            # Now, add some votes
            self.votecast_db.subscribe("MFIwEAYHKoZIzj0CAQYFK4EEABoDPgAEAIV8h+eS+vQ+0uqZNv3MYYTLo5s0JP+cmkvJ7U4JAHhfRv1wCqZSKIuY7Q+3ESezhRnnmmX4pbOVhKTU")
            self.votecast_db.spam("MFIwEAYHKoZIzj0CAQYFK4EEABoDPgAEAIV8h+eS+vQ+0uqZNv3MYYTLo5s0JP+cmkvJ7U4JAHhfRv1wCqZSKIuY7Q+3ESezhRnnmmX4pbOVhKTX")
            vote = {'mod_id':"MFIwEAYHKoZIzj0CAQYFK4EEABoDPgAEAIV8h+eS+vQ+0uqZNv3MYYTLo5s0JP+cmkvJ7U4JAHhfRv1wCqZSKIuY7Q+3ESezhRnnmmX4pbOVhKTU", 'voter_id':"MFIwEAYHKoZIzj0CAQYFK4EEABoDPgAEAIV8h+eS+vQ+0uqZNv3MYYTLo5s0JP+cmkvJ7U4JAHhfRv1wCqZSKIuY7Q+3ESezhRnnmmX4pbOVhKTX",'vote':1, 'time_stamp':132314}
            self.votecast_db.addVote(vote)
        except:
            print_exc()
        

    def tearDown(self):
        TestAsServer.tearDown(self)
        self.session.close_dbhandler(self.torrent_db)
      

    def get_default_torrent(self,filename,title,paths=None):
        metainfo = {}
        metainfo['announce'] = 'http://localhost:0/announce'
        metainfo['announce-list'] = []
        metainfo['creation date'] = int(time.time())
        metainfo['encoding'] = 'UTF-8'
        info = {}
        info['name'] = title.encode("UTF-8")
        info['piece length'] = 2 ** 16
        info['pieces'] = '*' * 20
        if paths is None:
            info['length'] = 481
        else:
            d1 = {}
            d1['path'] = [paths[0].encode("UTF-8")]
            d1['length'] = 201
            d2 = {}
            d2['path'] = [paths[1].encode("UTF-8")]
            d2['length'] = 280
            info['files'] = [d1,d2]
            
        metainfo['info'] = info
        path = os.path.join(self.config.get_torrent_collecting_dir(),filename)
        tdef = TorrentDef.load_from_dict(metainfo)
        tdef.save(path)
        return tdef, bencode(metainfo)


    def test_all(self):
        """ 
            I want to start a Tribler client once and then connect to
            it many times. So there must be only one test method
            to prevent setUp() from creating a new client every time.

            The code is constructed so unittest will show the name of the
            (sub)test where the error occured in the traceback it prints.
        """
        # test ChannelCast
        self.subtest_channelcast()
        
        # test VoteCast
        self.subtest_votecast()
        
        # test ChannelQuery-keyword
        self.subtest_channel_keyword_query()
        
        # test ChannelQuery-permid
        self.subtest_channel_permid_query()
        
        #test voting
        self.subtest_voting()

    def subtest_voting(self):
        self.votecast_db.unsubscribe(bin2str(self.mypermid))
        self.assertEqual(self.votecast_db.getVote(bin2str(self.mypermid),bin2str(self.hispermid)),None)
        #print >> sys.stderr, self.votecast_db.getAll()

        self.votecast_db.spam(bin2str(self.mypermid))
        self.assertEqual(self.votecast_db.getVote(bin2str(self.mypermid),bin2str(self.hispermid)),-1)
        #print >> sys.stderr, self.votecast_db.getAll()
                
        self.votecast_db.subscribe(bin2str(self.mypermid))
        self.assertEqual(self.votecast_db.getVote(bin2str(self.mypermid),bin2str(self.hispermid)),2)
        #print >> sys.stderr, self.votecast_db.getAll()
        
        self.votecast_db.unsubscribe(bin2str(self.mypermid))
        self.assertEqual(self.votecast_db.getVote(bin2str(self.mypermid),bin2str(self.hispermid)),None)
        #print >> sys.stderr, self.votecast_db.getAll()
        
        self.votecast_db.spam(bin2str(self.mypermid))
        self.assertEqual(self.votecast_db.getVote(bin2str(self.mypermid),bin2str(self.hispermid)),-1)
        #print >> sys.stderr, self.votecast_db.getAll()
        
    def check_chquery_reply(self, data):
        d = bdecode(data)
        self.assert_(type(d) == DictType)
        self.assert_(d.has_key('a'))
        self.assert_(d.has_key('id'))
        id = d['id']
        self.assert_(type(id) == StringType)
        self.assert_(validChannelCastMsg(d['a'])==True)

    def subtest_channel_permid_query(self):
        print >>sys.stderr,"test: chquery permid-----------------------------"
        s = OLConnection(self.my_keypair,'localhost',self.hisport)
        data = {}
        data['q'] = 'CHANNEL p '+ bin2str(self.hispermid)
        data['id'] = 'b' * 20
        msg = QUERY + bencode(data)
        s.send(msg)
        resp = s.recv()
        #print >> sys.stderr, "printing resp", resp
        if len(resp) > 0:
            print >>sys.stderr,"test: chquery: got",getMessageName(resp[0])
        self.assert_(resp[0]==QUERY_REPLY)
        self.check_chquery_reply(resp[1:])
        print>>sys.stderr,bdecode(resp[1:])
        s.close()
        
    def subtest_channel_keyword_query(self):
        print >>sys.stderr,"test: chquery keyword-----------------------------"
        s = OLConnection(self.my_keypair,'localhost',self.hisport)
        data = {}
        data['q'] = 'CHANNEL k tu'
        data['id'] = 'b' * 20
        msg = QUERY + bencode(data)
        s.send(msg)
        resp = s.recv()
        #print >> sys.stderr, "printing resp", resp
        if len(resp) > 0:
            print >>sys.stderr,"test: chquery: got",getMessageName(resp[0])
        self.assert_(resp[0]==QUERY_REPLY)
        self.check_chquery_reply(resp[1:])
        print>>sys.stderr,bdecode(resp[1:])
        s.close()
        
    def subtest_votecast(self):
        print >>sys.stderr,"test: votecast-----------------------------"
        s = OLConnection(self.my_keypair,'localhost',self.hisport)
        vcast = VoteCastCore(None, s, self.session, None, log = '', dnsindb = None)
        vdata = {}
        print >> sys.stderr, "sending vmsg", vdata
        msg = VOTECAST+bencode(vdata)
        s.send(msg)
        resp = s.recv()
        #print >> sys.stderr, "printing resp", resp
        if len(resp) > 0:
            print >>sys.stderr,"test: votecast: got",getMessageName(resp[0])
        self.assert_(resp[0]==VOTECAST)
        print >>sys.stderr, "test: votecast: got msg", bdecode(resp[1:])
        vdata_rcvd = bdecode(resp[1:])
        self.assert_(validVoteCastMsg(vdata_rcvd)==True)
        print>>sys.stderr, "End of votecast test"
        s.close()        
        
    def subtest_channelcast(self):
        print >>sys.stderr,"test: channelcast"
        s = OLConnection(self.my_keypair,'localhost',self.hisport)
        chcast = ChannelCastCore(None, s, self.session, None, log = '', dnsindb = None)
        #chdata = chcast.createChannelCastMessage()
        chdata = {}
        print >> sys.stderr, "sending chmsg", chdata
        msg = CHANNELCAST+bencode(chdata)
        s.send(msg)
        resp = s.recv()
        #print >> sys.stderr, "printing resp", resp
        if len(resp) > 0:
            print >>sys.stderr,"test: channelcast: got",getMessageName(resp[0])
        self.assert_(resp[0]==CHANNELCAST)
        print >>sys.stderr, "test: channelcast: got msg", bdecode(resp[1:])
        chdata_rcvd = bdecode(resp[1:])
        self.assert_(validChannelCastMsg(chdata_rcvd)==True)
        print>>sys.stderr, "End of channelcast test"
        s.close()        
        

def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestChannels))
    
    return suite

if __name__ == "__main__":
    unittest.main()
