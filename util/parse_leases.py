#!/usr/bin/env python

################################################################################
# parse_leases.py
# A script to parse an ISC dhcpd.leases file
# Author: Christopher Swingler
# Organization: South Side Hackerspace: Chicago
# Date: February 22 2014
################################################################################

# Though I was planning on doing this in native pickles, sqlite3 is part of the 
# stdlib and I do plan on searching it on different keys, so...
import sqlite3
from pyparsing import *
import datetime
import time
import calendar

# TODO: These need to be command-line parameters:
LEASEFILE='dhcpd.leases'
DYNAMIC_IP_RANGE='172.16.3.0/24'

class dhcpd_parser:

    lease_table_string = ""
    lt_conn = None
    lt_cursor = None


    def __init__(self):
        # Read in the lease table in ISC format
        # Set up the sqlite cursor
        # Create the empty table within
        self.lt_conn = sqlite3.connect('leases.sqlite')
        self.lt_cursor = self.lt_conn.cursor()
        self.create_lease_table_sql()
        self.build_lease_table('/users/Chris/dhcpd.leases')

    def __del__(self):
        # Destructor.
        self.lt_conn.commit()
        self.lt_conn.close()

    def create_lease_table_sql(self):
        # Do stuff
        # Delete the table if it exists:
        self.lt_cursor.execute('''DROP TABLE IF EXISTS leases''')
        # XXX: Warning: Naively presuming that MAC addresses are unique.
        # Actually, both mac AND IP should be unique.
        self.lt_cursor.execute('''CREATE TABLE leases (mac text PRIMARY KEY, ip text, host text, lease_start text, lease_end text, last_interaction text)''')
        self.lt_conn.commit()
        

    def build_lease_table(self, isc_lease_table_filename):
        # Okay, here's some fun facts about the dhcpd.leases file. Read 
        # dhcpd.leases(5) if you're bored.
        # * All times are UTC.
        # * A given hardware ethernet address can have multiple entries. The 
        #   last entry in the file is the valid one.
        # * Entires are not necessarily reaped for efficiency's sake, and new
        #   entries are always added at the bottom.
        # * The entire file is periodically destroyed and started from scratch.
        # * starts is the lease start, ends is the lease end, cltt is the time
        #   of last interactivity from the DHCP client (lessee). 

        # Notes: 
        # When inserting into the table, we'll want to use "INSERT OR REPLACE INTO butts VALUES ('Chris','fuzzy');" 
        # as anything that's in the file *later* than 

        lease_list = self.build_lease_list(isc_lease_table_filename)
        for lease in lease_list:
            start = self.convert_parsed_date_to_epoch(lease['lease_start'])
            print start

        return


    def convert_parsed_date_to_epoch(self, parsed_date):
        """
        Converts a parsed date from pyparser in the wacky format that's stored in
        ISC databases, and returns it as epoch time.
        """
        print parsed_date
        tdate = parsed_date[1]
        ttime = parsed_date[2]
        t = time.strptime("%s %s" % (tdate, ttime), "%Y/%m/%d %H:%M:%S")
        return calendar.timegm(t)




    def build_lease_list(self, isc_lease_table_filename):
        """
        Does the heavy lifting with pyparsing to process an ISC DHCPD leases file. 
        Returns a list of all the leases found.
        """

        # Parts of this are shamelessly stolen from: 
        # http://pyparsing.wikispaces.com/file/view/dhcpd_leases_parser.py/33450777/dhcpd_leases_parser.py
        # It needed a bit of work to properly digest modern ISC DHCPD lease databases.
        # Warning: This is a bit slow.

        f = open(isc_lease_table_filename)
        isc_db = f.read()

        LBRACE,RBRACE,SEMI,QUOTE = map(Suppress,'{};"')
        ipAddress = Combine(Word(nums) + ('.' + Word(nums))*3)
        hexint = Word(hexnums,exact=2)
        macAddress = Combine(hexint + (':'+hexint)*5)
        hdwType = Word(alphanums)

        yyyymmdd = Combine((Word(nums,exact=4)|Word(nums,exact=2))+
                            ('/'+Word(nums,exact=2))*2)
        hhmmss = Combine(Word(nums,exact=2)+(':'+Word(nums,exact=2))*2)
        dateRef = oneOf(list("0123456"))("weekday") + yyyymmdd("date") + \
                                                                hhmmss("time")

        startsStmt = "starts" + dateRef + SEMI
        endsStmt = "ends" + (dateRef | "never") + SEMI
        clttStmt = "cltt" + dateRef + SEMI
        tstpStmt = "tstp" + dateRef + SEMI
        tsfpStmt = "tsfp" + dateRef + SEMI
        hdwStmt = "hardware" + hdwType("type") + macAddress("mac") + SEMI
        uidStmt = "uid" + QuotedString('"')("uid") + SEMI
        bindingStmt = "binding" + Word(alphanums) + Word(alphanums) + SEMI
        rewindBindingStmt = "rewind binding" + Word(alphanums) + Word(alphanums) + SEMI
        nextBindingStmt = "next binding" + Word(alphanums) + Word(alphanums) + SEMI
        clientHostnameStmt = "client-hostname" + QuotedString('"') + SEMI


        leaseStatement = startsStmt | endsStmt | clttStmt | tstpStmt | tsfpStmt | hdwStmt | \
                            uidStmt | bindingStmt | nextBindingStmt | rewindBindingStmt | clientHostnameStmt

        leaseDef = "lease" + ipAddress("ipaddress") + LBRACE + \
                                    Dict(ZeroOrMore(Group(leaseStatement))) + RBRACE


        leases = []
        starttime = time.time()
        for lease in leaseDef.searchString(isc_db):
            thisLease = {}
            thisLease['mac'] = lease.hardware.mac
            thisLease['ip'] = lease.ipaddress
            thisLease['host'] = lease.get('client-hostname')
            thisLease['lease_start'] = lease.starts
            thisLease['lease_end'] = lease.ends
            thisLease['last_interaction'] = lease.cltt

            try:
                client_hostname = lease.client-hostname
            except NameError:
                client_hostname = None
            leases.append(thisLease)

        return leases

    def lease_active(self, start_time, end_time):
        """
        Given a lease start and end time (both in UTC), determine if this lease is still
        valid. Returns true or false.
        """
