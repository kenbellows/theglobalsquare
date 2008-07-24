# Written by Jie Yang
# see LICENSE.txt for license information

import sys
import os
from copy import deepcopy
from Queue import Queue, Empty 
from time import time, sleep
from base64 import encodestring, decodestring
import math
from random import shuffle
import threading
from traceback import print_exc, extract_stack, print_stack

# ONLY USE APSW >= 3.5.9-r1
import apsw
#support_version = (3,5,9)
#support_version = (3,3,13)
#apsw_version = tuple([int(r) for r in apsw.apswversion().split('-')[0].split('.')])
##print apsw_version
#assert apsw_version >= support_version, "Required APSW Version >= %d.%d.%d."%support_version + " But your version is %d.%d.%d.\n"%apsw_version + \
#                        "Please download and install it from http://code.google.com/p/apsw/"

CREATE_SQL_FILE = None
CREATE_SQL_FILE_POSTFIX = os.path.join('Tribler', 'tribler_sdb_v1.sql')
DB_FILE_NAME = 'tribler.sdb'
DB_DIR_NAME = 'sqlite'    # db file path = DB_DIR_NAME/DB_FILE_NAME
BSDDB_DIR_NAME = 'bsddb'
CURRENT_DB_VERSION = 1
DEFAULT_BUSY_TIMEOUT = 5000
MAX_SQL_BATCHED_TO_TRANSACTION = 1000   # don't change it unless carefully tested. A transaction with 1000 batched updates took 1.5 seconds
NULL = None
icon_dir = None
SHOW_ALL_EXECUTE = False
costs = []
cost_reads = []

def init(config, db_exception_handler = None):
    """ create sqlite database """
    global CREATE_SQL_FILE
    global icon_dir
    config_dir = config['state_dir']
    install_dir = config['install_dir']
    CREATE_SQL_FILE = os.path.join(install_dir,CREATE_SQL_FILE_POSTFIX)
    SQLiteCacheDB.exception_handler = db_exception_handler
    sqlitedb = SQLiteCacheDB.getInstance()   
    sqlite_db_path = os.path.join(config_dir, DB_DIR_NAME, DB_FILE_NAME)
    bsddb_path = os.path.join(config_dir, BSDDB_DIR_NAME)
    icon_dir = os.path.abspath(config['peer_icon_path'])
    sqlitedb.initDB(sqlite_db_path, CREATE_SQL_FILE, bsddb_path)  # the first place to create db in Tribler
    return sqlitedb
        
def done(config_dir):
    SQLiteCacheDB.getInstance().close()

def make_filename(config_dir,filename):
    if config_dir is None:
        return filename
    else:
        return os.path.join(config_dir,filename)    
    
def bin2str(bin):
    # Full BASE64-encoded 
    return encodestring(bin).replace("\n","")
    
def str2bin(str):
    return decodestring(str)

def print_exc_plus():
    """
    Print the usual traceback information, followed by a listing of all the
    local variables in each frame.
    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/52215
    http://initd.org/pub/software/pysqlite/apsw/3.3.13-r1/apsw.html#augmentedstacktraces
    """

    tb = sys.exc_info()[2]
    stack = []
    
    while tb:
        stack.append(tb.tb_frame)
        tb = tb.tb_next

    print_exc()
    print >> sys.stderr, "Locals by frame, innermost last"

    for frame in stack:
        print >> sys.stderr
        print >> sys.stderr, "Frame %s in %s at line %s" % (frame.f_code.co_name,
                                             frame.f_code.co_filename,
                                             frame.f_lineno)
        for key, value in frame.f_locals.items():
            print >> sys.stderr, "\t%20s = " % key,
            #We have to be careful not to cause a new error in our error
            #printer! Calling str() on an unknown object could cause an
            #error we don't want.
            try:                   
                print >> sys.stderr, value
            except:
                print >> sys.stderr, "<ERROR WHILE PRINTING VALUE>"

class safe_dict(dict): 
    def __init__(self, *args, **kw): 
        self.lock = threading.RLock() 
        dict.__init__(self, *args, **kw) 
        
    def __getitem__(self, key): 
        self.lock.acquire()
        try:
            return dict.__getitem__(self, key) 
        finally:
            self.lock.release()
            
    def __setitem__(self, key, value): 
        self.lock.acquire()
        try:
            dict.__setitem__(self, key, value) 
        finally:
            self.lock.release()
            
    def __delitem__(self, key): 
        self.lock.acquire()
        try:
            dict.__delitem__(self, key) 
        finally:
            self.lock.release()

    def __contains__(self, key):
        self.lock.acquire()
        try:
            return dict.__contains__(self, key) 
        finally:
            self.lock.release()
            
    def values(self):
        self.lock.acquire()
        try:
            return dict.values(self) 
        finally:
            self.lock.release()

class SQLiteCacheDB:
    
    __single = None    # used for multithreaded singletons pattern
    lock = threading.RLock()
    exception_handler = None
    cursor_table = safe_dict()    # {thread_name:cur}
    cache_transaction_table = safe_dict()   # {thread_name:[sql]
    class_variables = safe_dict({'db_path':None,'busytimeout':None})  # busytimeout is in milliseconds

    def getInstance(*args, **kw):
        # Singleton pattern with double-checking to ensure that it can only create one object
        if SQLiteCacheDB.__single is None:
            SQLiteCacheDB.lock.acquire()   
            try:
                if SQLiteCacheDB.__single is None:
                    SQLiteCacheDB(*args, **kw)
            finally:
                SQLiteCacheDB.lock.release()
        return SQLiteCacheDB.__single
    
    getInstance = staticmethod(getInstance)
    
    def __init__(self):
        # always use getInstance() to create this object
        if SQLiteCacheDB.__single != None:
            raise RuntimeError, "SQLiteCacheDB is singleton"
        SQLiteCacheDB.__single = self
        
        self.permid_id = safe_dict()    
        self.infohash_id = safe_dict()
        self.show_execute = False
        
        #TODO: All global variables must be protected to be thread safe?
        self.status_table = None
        self.category_table = None
        self.src_table = None
        
    def __del__(self):
        self.close()
    
    def close(self, clean=False):
        # only close the connection object in this thread, don't close other thread's connection object
        thread_name = threading.currentThread().getName()
        cur = self.getCursor(create=False)
        
        if cur:
            con = cur.getconnection()
            cur.close()
            con.close()
            con = None
            del SQLiteCacheDB.cursor_table[thread_name]
        if clean:    # used for test suite
            self.permid_id = safe_dict()
            self.infohash_id = safe_dict()
            SQLiteCacheDB.exception_handler = None
            SQLiteCacheDB.class_variables = safe_dict({'db_path':None,'busytimeout':None})
            SQLiteCacheDB.cursor_table = safe_dict()
            SQLiteCacheDB.cache_transaction_table = safe_dict()
            
            
    # --------- static functions --------
    def getCursor(self, create=True):
        thread_name = threading.currentThread().getName()
        curs = SQLiteCacheDB.cursor_table
        cur = curs.get(thread_name, None)    # return [cur, cur, lib] or None
        #print >> sys.stderr, '-------------- getCursor::', len(curs), time(), curs.keys()
        if cur is None and create:
            self.openDB(SQLiteCacheDB.class_variables['db_path'], SQLiteCacheDB.class_variables['busytimeout'])    # create a new db obj for this thread
            cur = curs.get(thread_name)
        
        return cur
       
    def openDB(self, dbfile_path=None, busytimeout=DEFAULT_BUSY_TIMEOUT):
        """ 
        Open a SQLite database. Only one and the same database can be opened.
        @dbfile_path       The path to store the database file. 
                           Set dbfile_path=':memory:' to create a db in memory.
        @busytimeout       Set the maximum time, in milliseconds, that SQLite will wait if the database is locked. 
        """

        # already opened a db in this thread, reuse it
        thread_name = threading.currentThread().getName()
        if thread_name in SQLiteCacheDB.cursor_table:
            #assert dbfile_path == None or SQLiteCacheDB.class_variables['db_path'] == dbfile_path
            return SQLiteCacheDB.cursor_table[thread_name]

        assert dbfile_path, "You must specify the path of database file"
        
        if dbfile_path.lower() != ':memory:':
            db_dir,db_filename = os.path.split(dbfile_path)
            if db_dir and not os.path.isdir(db_dir):
                os.makedirs(db_dir)            
        
        con = apsw.Connection(dbfile_path)
        con.setbusytimeout(busytimeout)

        cur = con.cursor()
        SQLiteCacheDB.cursor_table[thread_name] = cur
        return cur
    
    def createDBTable(self, sql_create_table, dbfile_path, busytimeout=DEFAULT_BUSY_TIMEOUT):
        """ 
        Create a SQLite database.
        @sql_create_tables The sql statements to create tables in the database. 
                           Every statement must end with a ';'.
        @dbfile_path       The path to store the database file. Set dbfile_path=':memory:' to creates a db in memory.
        @busytimeout       Set the maximum time, in milliseconds, that SQLite will wait if the database is locked.
                           Default = 10000 milliseconds   
        """
        cur = self.openDB(dbfile_path, busytimeout)
        cur.execute(sql_create_table)  # it is suggested to include begin & commit in the script

    def initDB(self, sqlite_filepath,
               create_sql_filename = None, 
               bsddb_dirpath = None, 
               busytimeout = DEFAULT_BUSY_TIMEOUT,
               check_version = True):
        """ 
        Create and initialize a SQLite database given a sql script. 
        Only one db can be opened. If the given dbfile_path is different with the opened DB file, warn and exit
        @configure_dir     The directory containing 'bsddb' directory 
        @sql_filename      The path of sql script to create the tables in the database
                           Every statement must end with a ';'. 
        @busytimeout       Set the maximum time, in milliseconds, to wait and retry 
                           if failed to acquire a lock. Default = 5000 milliseconds  
        """
        if create_sql_filename is None:
            create_sql_filename=CREATE_SQL_FILE
        try:
            SQLiteCacheDB.lock.acquire()

            # verify db path identity
            class_db_path = SQLiteCacheDB.class_variables['db_path']
            if sqlite_filepath == None:     # reuse the opened db file?
                if class_db_path != None:   # yes, reuse it
                    # reuse the busytimeout
                    return self.openDB(class_db_path, SQLiteCacheDB.class_variables['busytimeout'])
                else:   # no db file opened
                    raise Exception, "You must specify the path of database file when open it at the first time"
            else:
                if class_db_path == None:   # the first time to open db path, store it

                    if bsddb_dirpath != None and os.path.isdir(bsddb_dirpath) and not os.path.exists(sqlite_filepath):
                        self.convertFromBsd(bsddb_dirpath, sqlite_filepath, create_sql_filename)    # only one chance to convert from bsddb
                    #print 'quit now'
                    #sys.exit(0)
                    # open the db if it exists (by converting from bsd) and is not broken, otherwise create a new one
                    # it will update the db if necessary by checking the version number
                    self.safelyOpenTriblerDB(sqlite_filepath, create_sql_filename, busytimeout, check_version=check_version)
                    
                    SQLiteCacheDB.class_variables = {'db_path': sqlite_filepath, 'busytimeout': int(busytimeout)}
                    
                    return self.openDB()    # return the cursor, won't reopen the db
                    
                elif sqlite_filepath != class_db_path:  # not the first time to open db path, check if it is the same
                    raise Exception, "Only one database file can be opened. You have opened %s and are trying to open %s." % (class_db_path, sqlite_filepath) 
                        
        finally:
            SQLiteCacheDB.lock.release()

    def safelyOpenTriblerDB(self, dbfile_path, sql_create, busytimeout=DEFAULT_BUSY_TIMEOUT, check_version=False):
        """
        open the db if possible, otherwise create a new one
        update the db if necessary by checking the version number
        
        safeOpenDB():    
            try:
                if sqlite db doesn't exist:
                    raise Error
                open sqlite db
                read sqlite_db_version
                if sqlite_db_version dosen't exist:
                    raise Error
            except:
                close and delete sqlite db if possible
                create new sqlite db file without sqlite_db_version
                write sqlite_db_version at last
                commit
                open sqlite db
                read sqlite_db_version
                # must ensure these steps after except will not fail, otherwise force to exit
            
            if sqlite_db_version < current_db_version:
                updateDB(sqlite_db_version, current_db_version)
                commit
                update sqlite_db_version at last
                commit
        """

        try:
            if not os.path.isfile(dbfile_path):
                raise Exception
            
            cur = self.openDB(dbfile_path, busytimeout)
            if check_version:
                sqlite_db_version = self.readDBVersion()
                if sqlite_db_version == NULL or int(sqlite_db_version)<1:
                    raise NotImplementedError
        except:
            if os.path.isfile(dbfile_path):
                self.close(clean=True)
                os.remove(dbfile_path)
            
            if os.path.isfile(sql_create):
                f = open(sql_create)
                sql_create_tables = f.read()
                f.close()
            else:
                raise Exception, "Cannot open sql script at %s" % sql_create
            
            self.createDBTable(sql_create_tables, dbfile_path, busytimeout)  
            if check_version:
                sqlite_db_version = self.readDBVersion()
            
        if check_version:
            self.checkDB(sqlite_db_version, CURRENT_DB_VERSION)

    def report_exception(e):
        #return  # Jie: don't show the error window to bother users
        if SQLiteCacheDB.exception_handler != None:
            SQLiteCacheDB.exception_handler(e)

    def checkDB(self, db_ver, curr_ver):
        # read MyDB and check the version number.
        if not db_ver or not curr_ver:
            self.updateDB(db_ver,curr_ver)
            return
        db_ver = int(db_ver)
        curr_ver = int(curr_ver)
        #print "check db", db_ver, curr_ver
        if db_ver != curr_ver:    # TODO
            self.updateDB(db_ver,curr_ver)
            
    def updateDB(self,db_ver,curr_ver):
        pass    #TODO

    def readDBVersion(self):
        cur = self.getCursor()
        sql = "select value from MyInfo where entry='version'"
        res = self.fetchone(sql)
        if res:
            find = list(res)
            return find[0]    # throw error if something wrong
        else:
            return None
    
    report_exception = staticmethod(report_exception) 
    
    def show_sql(self, switch):
        # temporary show the sql executed
        self.show_execute = switch 
    
    # --------- generic functions -------------
        
    def commit(self):
        self.transaction()

    def _execute(self, sql, args=None):
        cur = self.getCursor()
        if SHOW_ALL_EXECUTE or self.show_execute:
            thread_name = threading.currentThread().getName()
            print >> sys.stderr, '===', thread_name, '===\n', sql, '\n-----\n', args, '\n======\n'
        try:
            if args is None:
                return cur.execute(sql)
            else:
                return cur.execute(sql, args)
        except Exception, msg:
            print_exc()
            print >> sys.stderr, "cachedb: execute error:", Exception, msg 
            #thread_name = threading.currentThread().getName()
            #print >> sys.stderr, '===', thread_name, '===\n', sql, '\n-----\n', args, '\n======\n'
            #raise Exception, msg
            return None

    def execute_read(self, sql, args=None):
        # this is only called for reading. If you want to write the db, always use execute_write, or executemany()
        return self._execute(sql, args)
    
    def execute_write(self, sql, args=None, commit=True):
        self.cache_transaction(sql, args)
        if commit:
            self.commit()
            
    def executemany(self, sql, args, commit=True):

        thread_name = threading.currentThread().getName()
        if thread_name not in SQLiteCacheDB.cache_transaction_table:
            SQLiteCacheDB.cache_transaction_table[thread_name] = []
        all = [(sql, arg) for arg in args]
        SQLiteCacheDB.cache_transaction_table[thread_name].extend(all)

        if commit:
            s = time()
            self.commit()
            
    def cache_transaction(self, sql, args=None):
        thread_name = threading.currentThread().getName()
        if thread_name not in SQLiteCacheDB.cache_transaction_table:
            SQLiteCacheDB.cache_transaction_table[thread_name] = []
        SQLiteCacheDB.cache_transaction_table[thread_name].append((sql, args))
                    
    def transaction(self, sql=None, args=None):
        if sql:
            self.cache_transaction(sql, args)
        
        thread_name = threading.currentThread().getName()
        
        n = 0
        sql_full = ''
        arg_list = []
        sql_queue = SQLiteCacheDB.cache_transaction_table.get(thread_name,None)
        if sql_queue:
            while True:
                try:
                    _sql,_args = sql_queue.pop(0)
                except IndexError:
                    break
                
                _sql = _sql.strip()
                if not _sql:
                    continue
                if not _sql.endswith(';'):
                    _sql += ';'
                sql_full += _sql + '\n'
                if _args != None:
                    arg_list += list(_args)
                n += 1
                
                # if too many sql in cache, split them into batches to prevent processing and locking DB for a long time
                # TODO: optimize the value of MAX_SQL_BATCHED_TO_TRANSACTION
                if n % MAX_SQL_BATCHED_TO_TRANSACTION == 0:
                    self._transaction(sql_full, arg_list)
                    sql_full = ''
                    arg_list = []
                    
            self._transaction(sql_full, arg_list)
            
    def _transaction(self, sql, args=None):
        if sql:
            sql = 'BEGIN TRANSACTION; \n' + sql + 'COMMIT TRANSACTION;'
            try:
                self._execute(sql, args)
            except Exception,e:
                self.commit_retry_if_busy_or_rollback(e,0) 
        
    def commit_retry_if_busy_or_rollback(self,e,tries):
        """ 
        Arno:
        SQL_BUSY errors happen at the beginning of the experiment,
        very quickly after startup (e.g. 0.001 s), so the busy timeout
        is not honoured for some reason. After the initial errors,
        they no longer occur.
        """
        if str(e).startswith("BusyError"):
            try:
                self._execute("COMMIT")
            except Exception,e2: 
                if tries < 5:   #self.max_commit_retries
                    # Spec is unclear whether next commit will also has 
                    # 'busytimeout' seconds to try to get a write lock.
                    sleep(pow(2.0,tries+2)/100.0)
                    self.commit_retry_if_busy_or_rollback(e2,tries+1)
                else:
                    self.rollback(cur, tries)
                    raise Exception,e2
        else:
            self.rollback(tries)
            m = "cachedb: TRANSACTION ERROR "+threading.currentThread().getName()+' '+str(e)
            raise Exception, m
            
            
    def rollback(self, tries):
        print_exc()
        try:
            self._execute("ROLLBACK")
        except Exception, e:
            # May be harmless, see above. Unfortunately they don't specify
            # what the error is when an attempt is made to roll back
            # an automatically rolled back transaction.
            m = "cachedb: ROLLBACK ERROR "+threading.currentThread().getName()+' '+str(e)
            #print >> sys.stderr, 'SQLite Database', m
            raise Exception, m
   
        
    # -------- Write Operations --------
    def insert(self, table_name, **argv):
        if len(argv) == 1:
            sql = 'INSERT INTO %s (%s) VALUES (?);'%(table_name, argv.keys()[0])
        else:
            questions = '?,'*len(argv)
            sql = 'INSERT INTO %s %s VALUES (%s);'%(table_name, tuple(argv.keys()), questions[:-1])
        self.execute_write(sql, argv.values())
    
    def insertMany(self, table_name, values, keys=None):
        """ values must be a list of tuples """

        questions = '?,'*len(values[0])
        if keys is None:
            sql = 'INSERT INTO %s VALUES (%s);'%(table_name, questions[:-1])
        else:
            sql = 'INSERT INTO %s %s VALUES (%s);'%(table_name, tuple(keys), questions[:-1])
        self.executemany(sql, values)
    
    def update(self, table_name, where=None, **argv):
        sql = 'UPDATE %s SET '%table_name
        for k in argv.keys():
            sql += '%s=?,'%k
        sql = sql[:-1]
        if where != None:
            sql += ' where %s'%where
        self.execute_write(sql, argv.values())
        
    def delete(self, table_name, **argv):
        sql = 'DELETE FROM %s WHERE '%table_name
        for k in argv:
            sql += '%s=? AND '%k
        sql = sql[:-5]
        self.execute_write(sql, argv.values())
    
    # -------- Read Operations --------
    def size(self, table_name):
        num_rec_sql = "SELECT count(*) FROM %s;"%table_name
        result = self.fetchone(num_rec_sql)
        return result

    def fetchone(self, sql, args=None):
        # returns NULL: if the result is null 
        # return None: if it doesn't found any match results
        find = self.execute_read(sql, args)
        if not find:
            return NULL
        else:
            find = list(find)
            if len(find) > 0:
                find = find[0]
            else:
                return NULL
        if len(find)>1:
            return find
        else:
            return find[0]
           
    def fetchall(self, sql, args=None, retry=0):
        res = self.execute_read(sql, args)
        if res != None:
            find = list(res)
            return find
        else:
            return []   # should it return None?
    
    def getOne(self, table_name, value_name, where=None, conj='and', **kw):
        """ value_name could be a string, a tuple of strings, or '*' 
        """

        if isinstance(value_name, tuple):
            value_names = ",".join(value_name)
        elif isinstance(value_name, list):
            value_names = ",".join(value_name)
        else:
            value_names = value_name
            
        if isinstance(table_name, tuple):
            table_names = ",".join(table_name)
        elif isinstance(table_name, list):
            table_names = ",".join(table_name)
        else:
            table_names = table_name
            
        sql = 'select %s from %s'%(value_names, table_names)
        
        if where or kw:
            sql += ' where '
        if where:
            sql += where
            if kw:
                sql += ' %s '%conj
        if kw:
            for k in kw:
                sql += ' %s=? '%k
                sql += conj
            sql = sql[:-len(conj)]
            arg = kw.values()
        else:
            arg = None
        #print >> sys.stderr, 'SQL: %s %s' % (sql, arg)
        return self.fetchone(sql,arg)
    
    def getAll(self, table_name, value_name, where=None, group_by=None, having=None, order_by=None, limit=None, offset=None, conj='and', **kw):
        """ value_name could be a string, or a tuple of strings 
            order by is represented as order_by
            group by is represented as group_by
        """

        if isinstance(value_name, tuple):
            value_names = ",".join(value_name)
        elif isinstance(value_name, list):
            value_names = ",".join(value_name)
        else:
            value_names = value_name
        
        if isinstance(table_name, tuple):
            table_names = ",".join(table_name)
        elif isinstance(table_name, list):
            table_names = ",".join(table_name)
        else:
            table_names = table_name
            
        sql = 'select %s from %s'%(value_names, table_names)
        
        if where or kw:
            sql += ' where '
        if where:
            sql += where
            if kw:
                sql += ' %s '%conj
        if kw:
            for k in kw:
                sql += ' %s=? '%k
                sql += conj
            sql = sql[:-len(conj)]
            arg = kw.values()
        else:
            arg = None
        
        if group_by != None:
            sql += ' group by ' + group_by
        if having != None:
            sql += ' having ' + having
        if order_by != None:
            sql += ' order by ' + order_by    # you should add desc after order_by to reversely sort, i.e, 'last_seen desc' as order_by
        if limit != None:
            sql += ' limit %d'%limit
        if offset != None:
            sql += ' offset %d'%offset

        try:
            return self.fetchall(sql, arg) or []
        except Exception, msg:
            print >> sys.stderr, "sqldb: Wrong getAll sql statement:", sql
            raise Exception, msg
    
    # ----- Tribler DB operations ----

    def convertFromBsd(self, bsddb_dirpath, dbfile_path, sql_filename, delete_bsd=False):
        # convert bsddb data to sqlite db. return false if cannot find or convert the db
        peerdb_filepath = os.path.join(bsddb_dirpath, 'peers.bsd')
        if not os.path.isfile(peerdb_filepath):
            return False
        else:
            print >> sys.stderr, "sqldb: ************ convert bsddb to sqlite", sql_filename
            converted = convert_db(bsddb_dirpath, dbfile_path, sql_filename)
            if converted is True and delete_bsd is True:
                print >> sys.stderr, "sqldb: delete bsddb directory"
                for filename in os.listdir(bsddb_dirpath):
                    if filename.endswith('.bsd'):
                        abs_path = os.path.join(bsddb_dirpath, filename)
                        os.remove(abs_path)
                try:
                    os.removedirs(bsddb_dirpath)   
                except:     # the dir is not empty
                    pass
        

    #------------- useful functions for multiple handlers ----------
    def insertPeer(self, permid, update=True, **argv):
        """ Insert a peer. permid is the binary permid.
        If the peer is already in db and update is True, update the peer.
        """
        peer_id = self.getPeerID(permid)
        peer_existed = False
        if peer_id != None:
            peer_existed = True
            if update:
                where='peer_id=%d'%peer_id
                self.update('Peer', where, **argv)
                #print >>sys.stderr,"sqldb: insertPeer: existing, updatePeer",`permid`
        else:
            #print >>sys.stderr,"********* sqldb: insertPeer, new",`permid`, argv
            self.insert('Peer', permid=bin2str(permid), **argv)
        return peer_existed
                
    def deletePeer(self, permid=None, peer_id=None, force=True):
        if peer_id is None:
            peer_id = self.getPeerID(permid)
            
        deleted = False
        if peer_id != None:
            if force:
                self.delete('Peer', peer_id=peer_id)
            else:
                self.delete('Peer', peer_id=peer_id, friend=0, superpeer=0)
            deleted = not self.hasPeer(permid, check_db=True)
            if deleted and permid in self.permid_id:
                self.permid_id.pop(permid)

        return deleted
                
    def getPeerID(self, permid):
        assert isinstance(permid, str), permid
        # permid must be binary
        if permid in self.permid_id:
            return self.permid_id[permid]
        
        sql_get_peer_id = "SELECT peer_id FROM Peer WHERE permid==?"
        peer_id = self.fetchone(sql_get_peer_id, (bin2str(permid),))
        if peer_id != None:
            self.permid_id[permid] = peer_id
        
        return peer_id
    
    def hasPeer(self, permid, check_db=False):
        if not check_db:
            return bool(self.getPeerID(permid))
        else:
            permid_str = bin2str(permid)
            sql_get_peer_id = "SELECT peer_id FROM Peer WHERE permid==?"
            peer_id = self.fetchone(sql_get_peer_id, (permid_str,))
            if peer_id is None:
                return False
            else:
                return True
    
    def insertInfohash(self, infohash, check_dup=False):
        """ Insert an infohash. infohash is binary """
        
        if infohash in self.infohash_id:
            if check_dup:
                print >> sys.stderr, 'sqldb: infohash to insert already exists', `infohash`
            return
        
        infohash_str = bin2str(infohash)
        sql_insert_torrent = "INSERT INTO Torrent (infohash) VALUES (?)"
        try:
            self.execute_write(sql_insert_torrent, (infohash_str,))
        except sqlite.IntegrityError, msg:
            if check_dup:
                print >> sys.stderr, 'sqldb:', sqlite.IntegrityError, msg, `infohash`
    
    def deleteInfohash(self, infohash=None, torrent_id=None):
        if torrent_id is None:
            torrent_id = self.getTorrentID(infohash)
            
        if torrent_id != None:
            self.delete('Torrent', torrent_id=torrent_id)
            if infohash in self.infohash_id:
                self.infohash_id.pop(infohash)
    
    def getTorrentID(self, infohash):
        assert isinstance(infohash, str), infohash
        if infohash in self.infohash_id:
            return self.infohash_id[infohash]
        
        sql_get_torrent_id = "SELECT torrent_id FROM Torrent WHERE infohash==?"
        tid = self.fetchone(sql_get_torrent_id, (bin2str(infohash),))
        if tid != None:
            self.infohash_id[infohash] = tid
        return tid
        
    def getInfohash(self, torrent_id):
        sql_get_infohash = "SELECT infohash FROM Torrent WHERE torrent_id==?"
        arg = (torrent_id,)
        ret = self.fetchone(sql_get_infohash, arg)
        ret = str2bin(ret)
        return ret
    
    def getTorrentStatusTable(self):
        if self.status_table is None:
            st = self.getAll('TorrentStatus', ('lower(name)', 'status_id'))
            self.status_table = dict(st)
        return self.status_table
    
    def getTorrentCategoryTable(self):
        # The key is in lower case
        if self.category_table is None:
            ct = self.getAll('Category', ('lower(name)', 'category_id'))
            self.category_table = dict(ct)
        return self.category_table
    
    def getTorrentSourceTable(self):
        # Don't use lower case because some URLs are case sensitive
        if self.src_table is None:
            st = self.getAll('TorrentSource', ('name', 'source_id'))
            self.src_table = dict(st)
        return self.src_table

    def test(self):
        res1 = self.getAll('Category', '*')
        res2 = len(self.getAll('Peer', 'name', 'name is not NULL'))
        return (res1, res2)

def convert_db(bsddb_dir, dbfile_path, sql_filename):
    # Jie: here I can convert the database created by the new Core version, but
    # what we should consider is to convert the database created by the old version
    # under .Tribler directory.
    print >>sys.stderr, "sqldb: start converting db from", bsddb_dir, "to", dbfile_path
    from bsddb2sqlite import Bsddb2Sqlite
    bsddb2sqlite = Bsddb2Sqlite(bsddb_dir, dbfile_path, sql_filename)
    global icon_dir
    return bsddb2sqlite.run(icon_dir=icon_dir)   

if __name__ == '__main__':
    configure_dir = sys.argv[1]
    config = {}
    config['state_dir'] = configure_dir
    config['install_dir'] = '.'
    config['peer_icon_path'] = '.'
    sqlite_test = init(config)
    sqlite_test.test()

