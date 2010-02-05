#!/bin/sh
#
# WARNING: this shell script must use \n as end-of-line, Windows
# \r\n gives problems running this on Linux

export PYTHONPATH=../..:"$PYTHONPATH"

# python test_bsddb2sqlite.py # Arno, 2008-11-26: Alea jacta est.
# python test_buddycast.py # currently not working due to missing DataHandler functions, 2008-10-17
# python test_friend.py # Arno, 2008-10-17: need to convert to new DB structure
# python test_sim.py # currently not working due to unfinished test functions, 2008-10-17
# python test_torrentcollecting.py # currently not working due to missing functions, 2009-12-04
python test_TimedTaskQueue.py
python test_bartercast.py
python test_cachingstream.py
python test_closedswarm.py
python test_connect_overlay.py singtest_connect_overlay
python test_crawler.py
python test_dialback_request.py
python test_extend_hs.py
python test_friendship_crawler.py
python test_g2g.py
python test_gui_server.py
python test_merkle.py
python test_multicast.py
python test_osutils.py
python test_permid.py
python test_permid_response1.py
python test_remote_query.py
python test_seeding_stats.py
python test_social_overlap.py
python test_sqlitecachedb.py
python test_status.py
python test_superpeers.py 
python test_url.py
python test_url_metadata.py
python test_ut_pex.py
python test_video_server.py

./test_buddycast2_datahandler.sh
./test_buddycast_msg.sh
./test_dialback_conn_handler.sh
./test_dialback_reply_active.sh
./test_dlhelp.sh
./test_friendship.sh          # See warning in test_friendship.py
./test_merkle_msg.sh
./test_overlay_bridge.sh
./test_rquery_reply_active.sh
./test_secure_overlay.sh
./test_sqlitecachedbhandler.sh
./test_vod.sh
sh ./test_na_extend_hs.sh

# Takes a long time, do at end
python test_natcheck.py

##### ARNO
# wait till arno's fixes are merged
# python test_buddycast5.py

#### NITIN
# wait till nitin fixes the testcase and the bin2str inconsistencies
# ./test_channelcast.sh
# python test_searchgridmanager.py

########### Not unittests
#
# 2010-02-03 Boudewijn: The stresstest works, but does not contain any
# actual unittests... it just takes a long time to run
# python test_buddycast4_stresstest.py
#
# 2010-02-03 Boudewijn: Doesn't look like this was ever a unittest
# python test_tracker_checking.py

########### Obsolete
#
# 2010-02-03 Boudewijn: Obsolete. test_cachedb.py tests the old
# bsdcachedb interface, no longer compatible with current code.
# python test_cachedb.py 
#
# 2010-02-03 Boudewijn: Obsolete. test_cachedbhandler.py tests the old
# bsdcachedb interface, no longer compatible with current code.
# python test_cachedbhandler.py
#
# 2010-02-03 Boudewijn: OLD, not using anymore
# python test_buddycast4.py 

