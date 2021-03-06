from random import choice
from string import letters
from time import time

from community import AllChannelCommunity
from Tribler.community.channel.community import ChannelCommunity
from Tribler.community.channel.preview import PreviewChannelCommunity

from Tribler.Core.dispersy.crypto import ec_generate_key, ec_to_public_bin, ec_to_private_bin
from Tribler.Core.dispersy.member import Member
from Tribler.Core.dispersy.script import ScriptBase
from Tribler.Core.dispersy.debug import Node
from Tribler.Core.dispersy.dprint import dprint
from lencoder import log  

from Tribler.Core.dispersy.script import ScenarioScriptBase

class AllChannelNode(Node):
    def create_channel_propagate(self, packets, global_time):
        meta = self._community.get_meta_message(u"channel-propagate")
        return meta.impl(distribution=(global_time,), payload=(packets,))

    def create_torrent_request(self, infohash, global_time):
        meta = self._community.get_meta_message(u"torrent-request")
        return meta.impl(distribution=(global_time,), payload=(infohash,))

class AllChannelScript(ScriptBase):
    def run(self):
        ec = ec_generate_key(u"low")                    
        self._my_member = Member.get_instance(ec_to_public_bin(ec), ec_to_private_bin(ec), sync_with_database=True)

        self.caller(self.test_incoming_channel_propagate)
        self.caller(self.test_outgoing_channel_propagate)

    def test_incoming_channel_propagate(self):
        """
        We will send a 'propagate-torrents' message from NODE to SELF with an infohash that is not
        in the local database, the associated .torrent should then be requested by SELF.
        """
        community = AllChannelCommunity.create_community(self._my_member)
        address = self._dispersy.socket.get_address()

        # create node and ensure that SELF knows the node address
        node = AllChannelNode()
        node.init_socket()
        node.set_community(community)
        node.init_my_member()
        yield 0.1

        # send a 'propagate-torrents' message with an infohash that SELF does not have
        packets = ["a"*22 for _ in range(10)]
        global_time = 10
        node.send_message(node.create_channel_propagate(packets, global_time), address)
        yield 0.1

        # # wait for the 'torrent-request' message from SELF to NODE
        # _, message = node.receive_message(addresses=[address], message_names=[u"torrent-request"])
        # assert message.payload.infohash == infohash

        # cleanup
        community.create_dispersy_destroy_community(u"hard-kill")

    def test_outgoing_channel_propagate(self):
        """
        We will send a 'propagate-torrents' message from SELF to NODE.

        Restrictions:
         - No duplicate infohashes.
         - No more than 50 infohashes.
         - At least 1 infohash must be given.
         - Infohashes must exist in SELF's database.
        """
        community = AllChannelCommunity.create_community(self._my_member)
        address = self._dispersy.socket.get_address()

        # wait for a few seconds for Tribler to collect some torrents...
        yield 5.0

        # create node and ensure that SELF knows the node address
        node = AllChannelNode()
        node.init_socket()
        node.set_community(community)
        node.init_my_member()
        yield 0.01

        # send a 'propagate-torrents' message
        community.create_channel_propagate()
        yield 0.01

        # wait for the 'propagate-torrents' message from SELF to NODE
        _, message = node.receive_message(addresses=[address], message_names=[u"propagate-torrents"])
        assert 1 <= len(message.payload.infohashes) <= 50, "to few or to many infohashes"
        assert len(set(message.payload.infohashes)) == len(message.payload.infohashes), "duplicate infohashes"

        dprint(map(lambda infohash: infohash.encode("HEX"), message.payload.infohashes), lines=1)

        # cleanup
        community.create_dispersy_destroy_community(u"hard-kill")

    # def test_incoming_torrent_request(self):
    #     """
    #     We will send a 'torrent-request' from NODE to SELF.
    #     """
    #     community = AllChannelCommunity.create_community(self._my_member)
    #     address = self._dispersy.socket.get_address()

    #     # wait for a few seconds for Tribler to collect some torrents...
    #     yield 5.0

    #     # create node and ensure that SELF knows the node address
    #     node = AllChannelNode()
    #     node.init_socket()
    #     node.set_community(community)
    #     node.init_my_member()
    #     yield 0.01

    #     # pick an existing infohash from the database
    #     infohash, = community._torrent_database._db.fetchone(u"SELECT infohash FROM Torrent ORDER BY RANDOM() LIMIT 1")
    #     dprint("requesting ", infohash.encode("HEX"))

    #     # send a 'torrent-request' message
    #     node.create_
    #     community.create_channel_propagate()
    #     yield 0.01

    #     # wait for the 'propagate-torrents' message from SELF to NODE
    #     _, message = node.receive_message(addresses=[address], message_names=[u"propagate-torrents"])
    #     assert 1 <= len(message.payload.infohashes) <= 50, "to few or to many infohashes"
    #     assert len(set(message.payload.infohashes)) == len(message.payload.infohashes), "duplicate infohashes"

    #     dprint(map(lambda infohash: infohash.encode("HEX"), message.payload.infohashes), lines=1)
    
    
class AllChannelScenarioScript(ScenarioScriptBase):
    def __init__(self, script, name, **kargs):
        ScenarioScriptBase.__init__(self, script, name, 'barter.log', **kargs)
        
        self.my_channel = None
        self.joined_community = None
        self.want_to_join = False
        self.torrentindex = 1

        self._dispersy.define_auto_load(ChannelCommunity, (), {"integrate_with_tribler":False})
        
    def join_community(self, my_member):
        self.my_member = my_member
        
        master_key = "3081a7301006072a8648ce3d020106052b81040027038192000403cbbfd2dfb67a7db66c88988df56f93fa6e7f982f9a6a0fa8898492c8b8cae23e10b159ace60b7047012082a5aa4c6e221d7e58107bb550436d57e046c11ab4f51f0ab18fa8f58d0346cc12d1cc2b61fc86fe5ed192309152e11e3f02489e30c7c971dd989e1ce5030ea0fb77d5220a92cceb567cbc94bc39ba246a42e215b55e9315b543ddeff0209e916f77c0d747".decode("HEX")
        master = Member.get_instance(master_key)

        assert my_member.public_key
        assert my_member.private_key
        assert master.public_key
        assert not master.private_key

        dprint("-master- ", master.database_id, " ", id(master), " ", master.mid.encode("HEX"), force=1)
        dprint("-my member- ", my_member.database_id, " ", id(my_member), " ", my_member.mid.encode("HEX"), force=1)

        return AllChannelCommunity.join_community(master, my_member, my_member, integrate_with_tribler = False)
    
    def execute_scenario_cmds(self, commands):
        torrents = []
        
        for command in commands:
            cur_command = command.split()
        
            if cur_command[0] == 'create':
                log(self._logfile, "creating-community")
                self.my_channel = ChannelCommunity.create_community(self.my_member, integrate_with_tribler = False)
                
                log(self._logfile, "creating-channel-message")
                self.my_channel.create_channel(u'', u'')
            
            elif cur_command[0] == 'publish':
                if self.my_channel:
                    infohash = str(self.torrentindex)
                    infohash += ''.join(choice(letters) for _ in xrange(20-len(infohash)))
                    
                    name = u''.join(choice(letters) for _ in xrange(100))
                    files = []
                    for _ in range(10):
                        files.append((u''.join(choice(letters) for _ in xrange(30)), 123455))
                    
                    trackers = []
                    for _ in range(10):
                        trackers.append(''.join(choice(letters) for _ in xrange(30))) 
                    
                    files = tuple(files)
                    trackers = tuple(trackers)
                    
                    self.torrentindex += 1
                    torrents.append((infohash, int(time()), name, files, trackers))
            
            elif cur_command[0] == 'post':
                if self.joined_community:
                    text = ''.join(choice(letters) for i in xrange(160))
                    self.joined_community._disp_create_comment(text, int(time()), None, None, None, None)
                
            elif cur_command[0] == 'join':
                self.want_to_join = True
                
        if self.want_to_join:
            from Tribler.Core.dispersy.dispersy import Dispersy
            dispersy = Dispersy.get_instance()
            
            log(self._logfile, "trying-to-join-community")
            
            for community in dispersy.get_communities():
                if isinstance(community, PreviewChannelCommunity) and community._channel_id:
                    self._community._disp_create_votecast(community.cid, 2, int(time()))
                    
                    log(self._logfile, "joining-community")
                    self.joined_community = community
                    
                    self.want_to_join = False
                    break
                
        if len(torrents) > 0:
            log(self._logfile, "creating-torrents")
            self.my_channel._disp_create_torrents(torrents)
