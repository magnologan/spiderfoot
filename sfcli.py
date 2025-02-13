#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:        sfcli
# Purpose:     Command Line Interface for SpiderFoot.
#
# Author:      Steve Micallef <steve@binarypool.com>
#
# Created:     03/05/2017
# Copyright:   (c) Steve Micallef 2017
# Licence:     GPL
# -------------------------------------------------------------------------------

import sys
import os
import re
import json
import requests
import shlex
import codecs
import time
import readline
import cmd
import argparse
from os.path import expanduser

# Colors to make things purty
class bcolors:
    GREYBLUE = '\x1b[38;5;25m'
    GREY = '\x1b[38;5;243m'
    DARKRED = '\x1b[38;5;124m'
    DARKGREEN = '\x1b[38;5;30m'
    BOLD = '\033[1m'
    ENDC = '\033[0m'
    GREYBLUE_DARK = '\x1b[38;5;24m'

class SpiderFootCli(cmd.Cmd):
    version = "3.0"
    pipecmd = None
    output = None
    modules = []
    types = []
    prompt = "sf> "
    nohelp = "[!] Unknown command '%s'."
    knownscans = []
    ownopts = {
        "cli.debug": False,
        "cli.silent": False,
        "cli.color": True,
        "cli.output": "pretty",
        "cli.history": True,
        "cli.history_file": "",
        "cli.spool": False,
        "cli.spool_file": "",
        "cli.username": "",
        "cli.password": "",
        "cli.server_baseurl": "http://127.0.0.1:5001"
    }

    def default(self, line):
        if line.startswith('#'):
            return

        self.edprint("Unknown command")

    # Auto-complete for these commands
    def complete_start(self, text, line, startidx, endidx):
        return self.complete_default(text, line, startidx, endidx)

    def complete_find(self, text, line, startidx, endidx):
        return self.complete_default(text, line, startidx, endidx)

    def complete_data(self, text, line, startidx, endidx):
        return self.complete_default(text, line, startidx, endidx)

    # Command completion for arguments
    def complete_default(self, text, line, startidx, endidx):
        ret = list()
        if "-m" in line and line.find("-m") > line.find("-t"):
            for m in self.modules:
                if m.startswith(text):
                    ret.append(m)

        if "-t" in line and line.find("-t") > line.find("-m"):
            for t in self.types:
                if t.startswith(text):
                    ret.append(t)
        return ret

    def dprint(self, msg, err=False, deb=False, plain=False, color=None):
        cout = ""
        sout = ""
        pfx = ""
        if err:
            pfx = "[!]"
            if self.ownopts['cli.color']:
                col = bcolors.DARKRED
        else:
            pfx = "[*]"
            if self.ownopts['cli.color']:
                col = bcolors.DARKGREEN
        if deb:
            if not self.ownopts["cli.debug"]:
                return
            pfx = "[+]"
            if self.ownopts['cli.color']:
                col = bcolors.GREY

        if color:
            pfx = ""
            col = color

        if err or not self.ownopts["cli.silent"]:
            if not plain or color:
                cout = col + bcolors.BOLD + pfx + " " + bcolors.ENDC + \
                       col +  msg + bcolors.ENDC
                # Never include color in the spool
                sout = pfx + " " + msg
            else:
                cout = msg
                sout = msg

            print(cout)

        if self.ownopts['cli.spool']:
            f = codecs.open(self.ownopts['cli.spool_file'], "a", encoding="utf-8")
            f.write(sout)
            f.write('\n')
            f.close()

    # Shortcut commands
    def do_debug(self, line):
        """debug
        Short-cut command for set cli.debug = 1"""
        if self.ownopts['cli.debug']:
            val = "0"
        else:
            val = "1"
        return self.do_set("cli.debug = " + val)

    def do_spool(self, line):
        """spool
        Short-cut command for set cli.spool = 1/0"""
        if self.ownopts['cli.spool']:
            val = "0"
        else:
            val = "1"
        if self.ownopts['cli.spool_file']:
            return self.do_set("cli.spool = " + val)
        else:
            self.edprint("You haven't set cli.spool_file. Set that before enabling spooling.")

    def do_history(self, line):
        """history [-l]
        Short-cut command for set cli.history = 1/0. 
        Add -l to just list the history."""
        c = self.myparseline(line)

        if '-l' in c[0]:
            i = 0
            while i < readline.get_current_history_length():
                self.dprint(readline.get_history_item(i), plain=True)
                i += 1
            return
        if self.ownopts['cli.history']:
            val = "0"
        else:
            val = "1"
        return self.do_set("cli.history = " + val)

    # Run before all commands to handle history and spooling
    def precmd(self, line):
        if self.ownopts['cli.history'] and line != "EOF":
            f = codecs.open(self.ownopts["cli.history_file"], "a", encoding="utf-8")
            f.write(line)
            f.write('\n')
            f.close()
        if self.ownopts['cli.spool']:
            f = codecs.open(self.ownopts["cli.spool_file"], "a", encoding="utf-8")
            f.write(self.prompt + line)
            f.write('\n')
            f.close()

        return line

    # Debug print
    def ddprint(self, msg):
        self.dprint(msg, deb=True)

    # Error print
    def edprint(self, msg):
        self.dprint(msg, err=True)

    # Print nice tables.
    def pretty(self, data, titlemap=None):
        out = list()
        # Get the column titles
        maxsize = dict()
        if type(data[0]) == dict:
            cols = data[0].keys()
        else:
            # for lists, use the index numbers as titles
            cols = map(str, range(0, len(data[0])))

        # Strip out columns that don't have titles
        if titlemap:
            nc = list()
            for c in cols:
                if c in titlemap:
                    nc.append(c)
            cols = nc

        spaces = 2
        # Find the maximum column sizes
        for r in data:
            i = 0
            for c in r:
                if type(r) == list:
                    # we have  list index
                    cn = str(i)
                    if type(c) == int:
                        v = str(c)
                    if type(c) == str:
                        v = unicode(c, errors='replace')
                    if type(c) == unicode:
                        v = c
                else:
                    # we have a dict key
                    cn = c
                    v = r[c]
                #print(str(cn) + ", " + str(c) + ", " + str(v))
                if len(v) > maxsize.get(cn, 0):
                    maxsize[cn] = len(v)
                i += 1


        # Adjust for long titles
        if titlemap:
            for c in maxsize:
                if len(titlemap.get(c, c)) > maxsize[c]:
                    maxsize[c] = len(titlemap.get(c, c))

        # Display the column titles
        i = 0
        for c in cols:
            if titlemap:
                t = titlemap.get(c, c)
            else:
                t = c
            #out += t
            out.append(t)
            sdiff = maxsize[c] - len(t) + 1
            #out += " " * spaces
            out.append(" " * spaces)
            if sdiff > 0 and i < len(cols)-1:
                #out += " " * sdiff
                out.append(" " * sdiff)
            i += 1
        #out += "\n"
        out.append('\n')

        # Then the separator
        i = 0
        for c in cols:
            #out += "-" * ((maxsize[c]+spaces))
            out.append("-" * ((maxsize[c]+spaces)))
            if i < len(cols)-1:
                #out += "+"
                out.append("+")
            i += 1
        #out += "\n"
        out.append("\n")

        # Then the actual data
        #ts = time.time()
        for r in data:
            i = 0
            di = 0
            tr = type(r)
            for c in r:
                if tr == list:
                    # we have  list index
                    cn = str(i)
                    tc = type(c)
                    if tc == int:
                        v = str(c)
                    if tc == str:
                        v = unicode(c, errors='replace')
                    if tc == unicode:
                        v = c
                else:
                    # we have a dict key
                    cn = c
                    v = r[c]
                if cn not in cols:
                    i += 1
                    continue

                out.append(v)
                lv = len(v)
                # there is a preceeding space if this is after the
                # first column
                # sdiff = number of spaces between end of word and |
                if di == 0:
                    sdiff = (maxsize[cn] - lv) + spaces
                else:
                    sdiff = (maxsize[cn] - lv) + spaces - 1
                if di < len(cols)-1:
                    #out += " " * sdiff
                    out.append(" " * sdiff)
                if di < len(cols)-1:
                    #out += "| "
                    out.append("| ")
                di += 1
                i += 1
            #out += "\n"
            out.append("\n")

        #print("time: " + str(time.time() - ts))
        #return ""
        return ''.join(out)

    # Make a request to the SpiderFoot server
    def request(self, url, post=None):
        #logging.basicConfig()
        #logging.getLogger().setLevel(logging.DEBUG)
        #requests_log = logging.getLogger("requests.packages.urllib3")
        #requests_log.setLevel(logging.DEBUG)
        #requests_log.propagate = True
        try:
            headers = {
                "User-agent": "SpiderFoot-CLI/" + self.version
            }

            self.ddprint("Fetching: " + url)
            self.ddprint("Posting: " + str(post))
            if not post:
                r = requests.get(url, 
                             headers = headers,
                             auth = requests.auth.HTTPDigestAuth(
                                        self.ownopts['cli.username'], 
                                        self.ownopts['cli.password']
                             )
                    )
            else:
                r = requests.post(url,
                             headers = headers,
                             auth = requests.auth.HTTPDigestAuth(
                                        self.ownopts['cli.username'],
                                        self.ownopts['cli.password']
                             ),
                             data = post
                    )
            self.ddprint("Response: " + str(r))
            if r.status_code == requests.codes.ok:  #pylint: disable=no-member
                return r.text
            else:
                r.raise_for_status()
        except BaseException as e:
            self.edprint("Failed communicating with server: " + str(e))
            return None

    def emptyline(self):
        return

    def completedefault(self, text, line, begidx, endidx):
        return []

    # Parse the command line, returns a list of lists:
    # sf> scans "blahblah test" | top 10 | grep foo ->
    # [[ 'blahblah test' ], [[ 'top', '10' ], [ 'grep', 'foo']]]
    def myparseline(self, cmdline, replace=True):
        ret = [list(),list()]
        s = shlex.split(cmdline.decode('string_escape'))
        for c in s:
            if c == '|':
                break
            if replace and c.startswith("$") and c in self.ownopts:
                ret[0].append(self.ownopts[c])
            else:
                ret[0].append(c)

        if s.count('|') == 0:
            return ret

        # Handle any pipe commands at the end
        ret[1] = list()
        i = 0
        ret[1].append(list())
        for t in s[(s.index('|')+1):]:
            if t == '|':
                i += 1
                ret[1].append(list())
                continue
            # Replace variables
            if t.startswith("$") and t in self.ownopts:
                ret[1][i].append(self.ownopts[t])
            else:
                ret[1][i].append(t)

        return ret

    # Send the command output to the user, proessing the pipes
    # that may have been used.
    def send_output(self, data, cmd, titles=None, total=True, raw=False):
        totalrec = 0
        out = None
        try:
            if not raw:
                j = json.loads(data)
                totalrec = len(j)
            else:
                j = data
        except BaseException as e:
            self.edprint("Unable to parse data from server: " + str(e))
            return

        if not raw:
            if self.ownopts['cli.output'] == "json":
                out = json.dumps(j, indent=4, separators=(',', ': '))

            if self.ownopts['cli.output'] == "pretty":
                out = self.pretty(j, titlemap=titles)

            if not out:
                self.edprint("Unknown output format '" + self.ownopts['cli.output'] + "'.")
                return
        else:
            out = data

        c = self.myparseline(cmd)

        # If no pipes, just disply the output
        if len(c[1]) == 0:
            self.dprint(out, plain=True)
            if total:
                self.dprint("Total records: " + str(totalrec))
            return
        
        for pc in c[1]:
            newout = ""
            if len(pc) == 0:
                self.edprint("Invalid syntax.")
                return
            pipecmd = pc[0]
            pipeargs = " ".join(pc[1:])
            if pipecmd not in [ "str", "regex", "file", "grep", "top", "last" ]:
                self.edprint("Unrecognised pipe command.")
                return

            if pipecmd == "regex":
                p = re.compile(pipeargs, re.IGNORECASE)
                for r in out.split("\n"):
                    if re.match(p, r.strip()):
                        newout += r + "\n"

            if pipecmd == "str" or pipecmd == "grep":
                for r in out.split("\n"):
                    if pipeargs.lower() in r.strip().lower():
                        newout += r + "\n"

            if pipecmd == "top":
                if not pipeargs.isdigit():
                    self.edprint("Invalid syntax.")
                    return
                newout = "\n".join(out.split("\n")[0:int(pipeargs)])
                
            if pipecmd == "last":
                if not pipeargs.isdigit():
                    self.edprint("Invalid syntax.")
                    return
                tot = len(out.split("\n"))
                i = tot - int(pipeargs)
                newout = "\n".join(out.split("\n")[i:])

            if pipecmd == "file":
                try:
                    f = codecs.open(pipeargs, "w", encoding="utf-8")
                    f.write(out)
                    f.close()
                except BaseException as e:
                    self.edprint("Unable to write to file: " + str(e))
                    return
                self.dprint("Successfully wrote to file '" + str(pipeargs) + "'.")
                return

            out = newout

        self.dprint(newout, plain=True)

    # Run SQL against the DB.
    def do_query(self, line):
        """query <SQL query>
        Run an <SQL query> against the database."""
        c = self.myparseline(line)
        if len(c[0]) < 1:
            self.edprint("Invalid syntax.")
            return
        query = ' '.join(c[0])
        d = self.request(self.ownopts['cli.server_baseurl'] + "/query",
                         post={"query": query})
        if not d:
            return
        j = json.loads(d)
        if j[0] == "ERROR":
            self.edprint("Error running your query: " + j[1])
            return
        self.send_output(d, line)

    # Ping the server.
    def do_ping(self, line):
        """ping
        Ping the SpiderFoot server to ensure it's responding."""
        d = self.request(self.ownopts['cli.server_baseurl'] + "/ping")
        if not d:
            return

        s = json.loads(d)
        if s[0] == "SUCCESS":
            self.dprint("Server " + self.ownopts['cli.server_baseurl'] + " responding.")
            self.do_modules("", cacheonly=True)
            self.do_types("", cacheonly=True)
        else:
            self.dprint("Something odd happened: " + str(d))

        if s[1] != self.version:
            self.edprint("Server and CLI version are not the same (" + s[1] + \
                        " / " + self.version + "). This could lead to unpredictable results!")

    # List all SpiderFoot modules.
    def do_modules(self, line, cacheonly=False):
        """modules
        List all available modules and their descriptions."""
        d = self.request(self.ownopts['cli.server_baseurl'] + "/modules")
        if not d:
            return
        if cacheonly:
            j = json.loads(d)
            for m in j:
                self.modules.append(m['name'])
            return
        self.send_output(d, line, titles={"name": "Module name",
                                          "descr": "Description"})

    # List all SpiderFoot data element types.
    def do_types(self, line, cacheonly=False):
        """types
        List all available element types and their descriptions."""
        d = self.request(self.ownopts['cli.server_baseurl'] + "/eventtypes")
        if not d:
            return
        if cacheonly:
            j = json.loads(d)
            for t in j:
                self.types.append(t[0])
            return
        self.send_output(d, line, titles={ "1": "Element description",
                                           "0": "Element name"})

    # Load commands from a file.
    def do_load(self, line):
        """load <file>
        Execute SpiderFoot CLI commands found in <file>."""
        pass

    # Get scan info and config.
    def do_scaninfo(self, line):
        """scaninfo <sid> [-c]
        Get status information for scan ID <sid>, optionally also its 
        configuration if -c is supplied."""
        c = self.myparseline(line)
        if len(c[0]) < 1:
            self.edprint("Invalid syntax.")
            return

        sid = c[0][0]
        d = self.request(self.ownopts['cli.server_baseurl'] + "/scanopts?id=" + sid)
        if not d:
            return
        j = json.loads(d)
        if len(j) == 0:
            self.dprint("No such scan exists.")
            return

        out  = "Name: " + j['meta'][0] + "\n"
        out += "ID: " + sid + "\n"
        out += "Target: " + j['meta'][1] + "\n"
        out += "Started: " + j['meta'][3] + "\n"
        out += "Completed: " + j['meta'][4] + "\n"
        out += "Status: " + j['meta'][5] + "\n"

        if "-c" in c[0]:
            out += "Configuration:\n"
            for k in sorted(j['config']):
                out += "  " + k + " = " + j['config'][k] + "\n"

        self.send_output(out, line, total=False, raw=True)

    # List scans.
    def do_scans(self, line):
        """scans [-x]
        List all scans, past and present. -x for extended view."""
        d = self.request(self.ownopts['cli.server_baseurl'] + "/scanlist")
        if not d:
            return
        j = json.loads(d)
        if len(j) == 0:
            self.dprint("No scans exist.")
            return
   
        c = self.myparseline(line)
        titles = dict()
        if "-x" in c[0]:
            titles = {"0": "ID",
              "1": "Name",
              "2": "Target",
              "4": "Started",
              "5": "Finished",
              "6": "Status",
              "7": "Total Elements"
            }
        else:
            titles = {
              "0": "ID",
              "2": "Target",
              "6": "Status",
              "7": "Total Elements"
            }

        self.send_output(d, line, titles=titles)

    # Show the data from a scan.
    def do_data(self, line):
        """data <sid> [-t type] [-x] [-u]
        Get the scan data for scan ID <sid> and optionally the element 
        type [type] (e.g. EMAILADDR), [type]. Use -x for extended format. 
        Use -u for a unique set of results."""
        c = self.myparseline(line)
        if len(c[0]) < 1:
            self.edprint("Invalid syntax.")
            return

        post = { "id": c[0][0] }

        if "-t" in c[0]:
            post["eventType"] = c[0][c[0].index("-t")+1]
        else:
            post["eventType"] = "ALL"

        if "-u" in c[0]:
            url = self.ownopts['cli.server_baseurl'] + "/scaneventresultsunique"
        else:
            url = self.ownopts['cli.server_baseurl'] + "/scaneventresults"

        d = self.request(url, post=post)
        if not d:
            return
        j = json.loads(d)
        if len(j) < 1:
            self.dprint("No results.")
            return

        if "-u" in c[0]:
            titles={
                    "0": "Data"
            }
        else:
            titles={
                    "10": "Type",
                    "1": "Data" 
            }
        if "-x" in c[0]:
            titles["0"] = "Last Seen"
            titles["3"] = "Module"
            titles["2"] = "Source Data"
        d = d.replace("&lt;/SFURL&gt;", "").replace("&lt;SFURL&gt;","")
        self.send_output(d, line, titles=titles)

    # Show logs.
    def do_logs(self, line):
        """logs <sid> [-l count] [-w]
        Show the most recent [count] logs for a given scan ID, <sid>. 
        If no count is supplied, all logs are given.
        If -w is supplied, logs will be streamed to the console until 
        Ctrl-C is entered."""
        c = self.myparseline(line)
        if len(c[0]) < 1:
            self.edprint("Invalid syntax.")
            return
        sid = c[0][0] 
        limit = None
        if "-l" in c[0]:
            limit = c[0][c[0].index("-l")+1]

        if "-w" not in c[0]:
            d = self.request(self.ownopts['cli.server_baseurl'] + "/scanlog",
                             post={ 'id': sid, 'limit': limit })
            if not d:
                return
            j = json.loads(d)
            if len(j) < 1:
                self.dprint("No results.")
                return

            self.send_output(d, line, titles={"0": "Generated",
                                              "1": "Type",
                                              "2": "Source",
                                              "3": "Message"
                                      }
                            )
            return
        else:
            # Get the rowid of the latest log message
            d = self.request(self.ownopts['cli.server_baseurl'] + "/scanlog",
                             post={'id': sid, 'limit': '1'})
            if not d:
                return
            j = json.loads(d)
            if len(j) < 1:
                self.dprint("No logs (yet?).")
                return
            else:
                rowid = j[0][4]

            try:
                if not limit:
                    limit = 10
                d = self.request(self.ownopts['cli.server_baseurl'] + "/scanlog",
                                 post={'id': sid, 'reverse': '1', 'rowId': rowid-int(limit)})
                if not d:
                    return
                j = json.loads(d)
                for r in j:
                    #self.send_output(str(r), line, total=False, raw=True)
                    if r[2] == "ERROR":
                        self.edprint(r[1] + ": " + r[3])
                    else:
                        self.dprint(r[1] + ": " + r[3])
 
                while True:
                    d = self.request(self.ownopts['cli.server_baseurl'] + "/scanlog",
                                     post={'id': sid, 'reverse': '1', 'rowId': rowid})
                    if not d:
                        return
                    j = json.loads(d)
                    for r in j:
                        if r[2] == "ERROR":
                            self.edprint(r[1] + ": " + r[3])
                        else:
                            self.dprint(r[1] + ": " + r[3])

                        rowid = str(r[4])
                    time.sleep(0.5)
            except KeyboardInterrupt:
                return

    # Start a new scan.
    def do_start(self, line):
        """start <target> (-m m1,... | -t t1,... | -u case) [-n name] [-w]
        Start a scan against <target> using modules m1,... OR looking 
        for types t1,...
        OR by use case ("all", "investigate", "passive" and "footprint").

        Scan be be optionally named [name], without a name the target 
        will be used.
        Use -w to watch the logs from the scan. Ctrl-C to abort the 
        logging (but will not abort the scan).
        """
        mods = ""
        types = ""
        usecase = ""
        c = self.myparseline(line)
        if len(c[0]) < 3:
            self.edprint("Invalid syntax.")
            return

        if "-m" in c[0]:
            mods = c[0][c[0].index("-m")+1]

        if "-t" in c[0]:
            # Scan by type
            types = c[0][c[0].index("-t")+1]

        if "-u" in c[0]:
            # Scan by use case
            usecase = c[0][c[0].index("-u")+1]

        if not mods and not types and not usecase:
            self.edprint("Invalid syntax.")
            return

        target = c[0][0]
        if "-n" in c[0]:
            title = c[0][c[0].index("-n")+1]
        else:
            title = target

        post = { "scanname": title,
                 "scantarget": target,
                 "modulelist": mods,
                 "typelist": types,
                 "usecase": usecase,
                 "cli": "1"
        }
        d = self.request(self.ownopts['cli.server_baseurl'] + "/startscan",
                         post=post)
        if not d:
            return

        s = json.loads(d)
        if s[0] == "SUCCESS":
            self.dprint("Successfully initiated scan.")
            self.dprint("Scan ID: " + s[1])
        else:
            self.dprint("Unable to start scan: " + str(s[1]))

        if "-w" in c[0]:
            return self.do_logs(s[1] + " -w")

    # Stop a running scan.
    def do_stop(self, line):
        """stop <sid>
        Abort the running scan with scan ID, <sid>."""
        c = self.myparseline(line)
        try:
            id = c[0][0]
        except BaseException as e:
            self.edprint("Invalid syntax.")
            return

        d = self.request(self.ownopts['cli.server_baseurl'] + \
                         "/stopscan?id=" + id + "&cli=1")
        if not d:
            return

        s = json.loads(d)
        if s[0] == "SUCCESS":
            self.dprint("Successfully requested scan to stop. This could take some minutes to complete.")
        else:
            self.dprint("Unable to stop scan: " + str(s[1]))

    # Search for data, alias to find
    def do_search(self, line):
        """search (look up 'find')
        """
        return self.do_find(line)

    # Search for data
    def do_find(self, line):
        """find "<string|/regex/>" <[-s sid]|[-t type]> [-x]
        Search for string/regex, limited to the scope of either a scan ID or 
        event type. -x for extended format."""
        c = self.myparseline(line)
        if len(c[0]) < 1:
            self.edprint("Invalid syntax.")
            return

        val = c[0][0]
        sid = None
        etype = None
        if "-t" in c[0]:
            etype = c[0][c[0].index("-t")+1]
        if "-s" in c[0]:
            sid = c[0][c[0].index("-s")+1]

        titles={"0": "Last Seen",
                "1": "Data",
                "3": "Module"
        }
        if "-x" in c[0]:
            titles["2"] = "Source Data"

        d = self.request(self.ownopts['cli.server_baseurl'] + "/search",
                         post={'value': val, 'id': sid, 'eventType': etype})
        if not d:
            return
        j = json.loads(d)

        if not j:
            self.dprint("No results found.")
            return
        if len(j) < 1:
            self.dprint("No results found.")
            return

        self.send_output(d, line, titles)

    # Summary of a scan
    def do_summary(self, line):
        """summary <sid> [-t]
        Summarise the results for a scan ID, <sid>. -t to only show 
        the element types."""
        c = self.myparseline(line)
        if len(c[0]) < 1:
            self.edprint("Invalid syntax.")
            return

        sid = c[0][0]

        if "-t" in c[0]:
            titles = {"0": "Element Type"}
        else:
            titles={"0": "Element Type",
                    "1": "Element Description",
                    "3": "Total",
                    "4": "Unique"
            }

        d = self.request(self.ownopts['cli.server_baseurl'] + "/scansummary?id=" + sid + "&by=type")
        if not d:
            return
        j = json.loads(d)

        if not j:
            self.dprint("No results found.")
            return
        if len(j) < 1:
            self.dprint("No results found.")
            return

        self.send_output(d, line, titles, total=False)

    # Delete a scan
    def do_delete(self, line):
        """delete <sid>
        Delete a scan with scan ID, <sid>."""
        c = self.myparseline(line)
        try:
            id = c[0][0]
        except BaseException as e:
            self.edprint("Invalid syntax.")
            return

        d = self.request(self.ownopts['cli.server_baseurl'] + \
                         "/scandelete?confirm=1&raw=1&id=" + id)
        if not d:
            return

        s = json.loads(d)
        if s[0] == "SUCCESS":
            self.dprint("Successfully deleted scan.")
        else:
            self.dprint("Something odd happened: " + str(s[1]))

    # Override the default help
    def print_topics(self, header, cmds, cmdlen, maxcol):
        if not cmds:
            return

        helpmap = [
            ["help [command]", "This help output."],
            ["debug", "Enable/Disable debug output."],
            ["clear", "Clear the screen."],
            ["history", "Enable/Disable/List command history."],
            ["spool", "Enable/Disable spooling output."],
            ["shell", "Execute a shell command."],
            ["exit", "Exit the SpiderFoot CLI (won't impact running scans)."],
            ["ping", "Test connectivity to the SpiderFoot server."],
            ["modules", "List available modules."],
            ["types", "List available data types."],
            ["set", "Set variables and configuration settings."],
            ["scans", "List all scans that have been run or are running."],
            ["start", "Start a new scan."],
            ["stop", "Stop a scan."],
            ["delete", "Delete a scan."],
            ["scaninfo", "Scan information."],
            ["data", "Show data from a scan's results."],
            ["summary", "Scan result summary."],
            ["find", "Search for data within scan results."],
            ["query", "Run SQL against the SpiderFoot SQLite database."],
            ["logs", "View/watch logs from a scan."]
        ]

        self.send_output(json.dumps(helpmap), "", titles={"0": "Command", "1": "Description"},
                         total=False)

    # Get/Set configuration
    def do_set(self, line):
        """set [opt [= <val>]]
        Set a configuration variable in SpiderFoot."""

        c = self.myparseline(line, replace=False)
        cfg = None
        val = None

        if len(c[0]) > 0:
            cfg = c[0][0]

        if len(c[0]) > 2:
            try:
                val = c[0][2]
            except BaseException as e:
                self.edprint("Invalid syntax.")
                return

        # Get the server-side config
        d = self.request(self.ownopts['cli.server_baseurl'] + "/optsraw")
        if not d:
            return
        j = list()
        serverconfig = dict()
        token = ""
        if not d:
            self.edprint("Unable to obtain SpiderFoot server-side config.")
        else:
            j = json.loads(d)
            if j[0] == "ERROR":
                self.edprint("Error fetching SpiderFoot server-side config.")
                return
            else:
                serverconfig = j[1]['data']
                token = j[1]['token']

        self.ddprint(str(serverconfig))

        if not cfg or not val:
            ks = self.ownopts.keys()
            ks.sort()
            output = list()
            for k in ks:
                c = self.ownopts[k]
                if type(c) == bool:
                    if c:
                        c = "True"
                    else:
                        c = "False"

                if not cfg:
                    output.append({'opt': k, 'val': c})
                else:
                    if cfg == k:
                        self.dprint(k + " = " + c, plain=True)

            for k in sorted(serverconfig.keys()):
                if type(serverconfig[k]) == list:
                    serverconfig[k] = ','.join(serverconfig[k])
                if not cfg:
                    output.append({'opt': k, 'val': str(serverconfig[k])})
                else:
                    if cfg == k:
                        self.dprint(k + " = " + str(serverconfig[k]), plain=True)

            if len(output) > 0:
                self.send_output(json.dumps(output), line, 
                                 { 'opt': "Option", 'val': "Value"}, 
                                 total=False)
            return

        if val:
            # Local CLI config
            if cfg in self.ownopts or cfg.startswith('$'):
                if not cfg.startswith('$'):
                    if type(self.ownopts[cfg]) == bool:
                        if val.lower() == "false" or val == "0":
                            val = False
                        else:
                            val = True

                self.ownopts[cfg] = val
                self.dprint(cfg + " set to " + str(val))
                return
            # Server-side config
            else:
                # submit all non-CLI vars to the SF server
                confdata = dict()
                found = False
                for k in serverconfig:
                    if k == cfg:
                        serverconfig[k] = val
                        found = True

                if not found:
                    self.edprint("Variable not found, so not set.")
                    return

                # Sanitize the data before sending it to the server
                for k in serverconfig:
                    optstr = ":".join(k.split(".")[1:])
                    if type(serverconfig[k]) == bool:
                        if not serverconfig[k]:
                            confdata[optstr] = "0"
                        else:
                            confdata[optstr] = "1"
                    if type(serverconfig[k]) == list:
                        # If set by the user, it must already be a 
                        # string, not a list
                        confdata[optstr] = ','.join(serverconfig[k])
                    if type(serverconfig[k]) == int:
                        confdata[optstr] = str(serverconfig[k])
                    if type(serverconfig[k]) in [ str, unicode ]:
                        confdata[optstr] = serverconfig[k]
    
                self.ddprint(str(confdata))
                d = self.request(self.ownopts['cli.server_baseurl'] + "/savesettingsraw",
                                 post={'token': token,'allopts': json.dumps(confdata)})
                j = list()
                if not d:
                    self.edprint("Unable to set SpiderFoot server-side config.")
                    return
                else:
                    j = json.loads(d)
                    if j[0] == "ERROR":
                        self.edprint("Error setting SpiderFoot server-side config: " + str(j[1]))
                        return
                    self.dprint(cfg + " set to " + str(val))
                    return

        if cfg not in self.ownopts:
            self.edprint("Variable not found, so not set. Did you mean to use a $ variable?")
            return

    # Execute a shell command locally and return the output
    def do_shell(self, line):
        """shell
        Run a shell command locally."""
        self.dprint("Running shell command:" + str(line))
        self.dprint(os.popen(line).read(), plain=True)

    def do_clear(self, line):
        """clear
        Clear the screen."""
        sys.stderr.write("\x1b[2J\x1b[H")

    # Exit the CLI
    def do_exit(self, line):
        """exit
        Exit the SpiderFoot CLI."""
        return True

    # Ctrl-D
    def do_EOF(self, line):
        """EOF (Ctrl-D)
        Exit the SpiderFoot CLI."""
        print("\n")
        return True

if __name__ == "__main__":
    p = argparse.ArgumentParser(description='SpiderFoot: Open Source Intelligence Automation.')
    p.add_argument("-d", "--debug", help="Enable debug output.", action='store_true')
    p.add_argument("-s", metavar="URL", type=str, help="Connect to SpiderFoot server on URL. By default, a connection to http://127.0.0.1:5001 will be attempted.")
    p.add_argument("-u", metavar="USER", type=str, help="Username to authenticate to SpiderFoot server.")
    p.add_argument("-p", metavar="PASS", type=str, help="Password to authenticate to SpiderFoot server. Consider using -P PASSFILE instead so that your password isn't visible in your shell history or in process lists!")
    p.add_argument("-P", metavar="PASSFILE", type=str, help="File containing password to authenticate to SpiderFoot server. Ensure permissions on the file are set appropriately!")
    p.add_argument("-e", metavar="FILE", type=str, help="Execute commands from FILE.")
    p.add_argument("-l", metavar="FILE", type=str, help="Log command history to FILE. By default, history is stored to ~/.spiderfoot_history unless disabled with -n.")
    p.add_argument("-n", action='store_true', help="Disable history logging.")
    p.add_argument("-o", metavar="FILE", type=str, help="Spool commands and output to FILE.")
    p.add_argument("-q", help="Silent output, only errors reported.", action='store_true')
    p.add_argument("-k", help="Turn off color-coded output.", action='store_true')
    p.add_argument("-b", "-v", help="Print the banner w/ version and exit.", action='store_true')

    args = p.parse_args()

    # Load commands from a file
    if args.e:
        try:
            cin = open(args.e, "r")
        except BaseException as e:
            print("Unable to open " + args.e + ":" + " (" + str(e) + ")")
            sys.exit(-1)
    else:
        cin = sys.stdin
    s = SpiderFootCli(stdin=cin)
    s.identchars += "$"

    # Map command-line to config
    if args.u:
        s.ownopts['cli.username'] = args.u
    if args.p:
        s.ownopts['cli.password'] = args.p
    if args.P:
        try:
            pf = open(args.P, "r")
            s.ownopts['cli.password'] = pf.readlines()[0].strip('\n')
            pf.close()
        except BaseException as e:
            print("Unable to open " + args.P + ":" + " (" + str(e) + ")")
            sys.exit(-1)
    if args.k:
        s.ownopts['cli.color'] = False
    if args.s:
        s.ownopts['cli.server_baseurl'] = args.s
    if args.debug:
        s.ownopts['cli.debug'] = True
    if args.q:
        s.ownopts['cli.silent'] = True
    if args.n:
        s.ownopts['cli.history'] = False
    if args.l:
        s.ownopts['cli.history_file'] = args.l
    else:
        try:
            s.ownopts['cli.history_file'] = expanduser("~") + "/.spiderfoot_history"
        except BaseException as e:
            s.ownopts['cli.history_file'] = ".spiderfoot_history"
    if args.o:
        s.ownopts['cli.spool'] = True
        s.ownopts['cli.spool_file'] = args.o

    if args.e or not os.isatty(0):
        try:
            s.use_rawinput = False
            s.prompt = ""
            s.cmdloop()
        finally:
            cin.close()
        sys.exit(0)

    if not args.q:
        s = SpiderFootCli()
        s.dprint("\n\
  _________      .__    .___          ___________            __  \n\
 /   _____/_____ |__| __| _/__________\\_   _____/___   _____/  |_ \n\
 \_____  \\\\____ \|  |/ __ |/ __ \\_  __ \\    __)/  _ \ /  _ \\   __\\\n\
 /        \\  |_> >  / /_/ \\  ___/|  | \\/     \\(  <_> |  <_> )  |  \n\
/_______  /   __/|__\\____ |\\___  >__|  \\___  / \\____/ \\____/|__|  \n\
        \\/|__|           \\/    \\/          \\/                     \n\
                Open Source Intelligence Automation.", plain=True, 
                color=bcolors.GREYBLUE)
        s.dprint("\
               by Steve Micallef | @binarypool\n", plain=True, 
                 color=bcolors.GREYBLUE_DARK)
        s.dprint("Version " + s.version + ".")
        if args.b:
            sys.exit(0)

    # Test connectivity to the server
    s.do_ping("")
        
    if not args.n:
        try:
            f = codecs.open(s.ownopts['cli.history_file'], "r", encoding="utf-8")
            for line in f.readlines():
                readline.add_history(line.strip())
            s.dprint("Loaded previous command history.")
        except BaseException as e:
            pass

    s.dprint("Type 'help' or '?'.")
    s.cmdloop()
