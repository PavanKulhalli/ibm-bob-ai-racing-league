#!/usr/bin/python
# snakeoil.py
# Chris X Edwards <snakeoil@xed.ch>
# Snake Oil is a Python library for interfacing with a TORCS
# race car simulator which has been patched with the server
# extentions used in the Simulated Car Racing competitions.
# http://scr.geccocompetitions.com/
#
# To use it, you must import it and create a "drive()" function.
# This will take care of option handling and server connecting, etc.
# To see how to write your own client do something like this which is
# a complete working client:
# /-----------------------------------------------\
# |#!/usr/bin/python                              |
# |import snakeoil                                |
# |if __name__ == "__main__":                     |
# |    C= snakeoil.Client()                       |
# |    for step in xrange(C.maxSteps,0,-1):       |
# |        C.get_servers_input()                  |
# |        snakeoil.drive_example(C)              |
# |        C.respond_to_server()                  |
# |    C.shutdown()                               |
# \-----------------------------------------------/
# This should then be a full featured client. The next step is to
# replace 'snakeoil.drive_example()' with your own. There is a
# dictionary which holds various option values (see `default_options`
# variable for all the details) but you probably only need a few
# things from it. Mainly the `trackname` and `stage` are important
# when developing a strategic bot.
#
# This dictionary also contains a ServerState object
# (key=S) and a DriverAction object (key=R for response). This allows
# you to get at all the information sent by the server and to easily
# formulate your reply. These objects contain a member dictionary "d"
# (for data dictionary) which contain key value pairs based on the
# server's syntax. Therefore, you can read the following:
#    angle, curLapTime, damage, distFromStart, distRaced, focus,
#    fuel, gear, lastLapTime, opponents, racePos, rpm,
#    speedX, speedY, speedZ, track, trackPos, wheelSpinVel, z
# The syntax specifically would be something like:
#    X= o[S.d['tracPos']]
# And you can set the following:
#    accel, brake, clutch, gear, steer, focus, meta
# The syntax is:
#     o[R.d['steer']]= X
# Note that it is 'steer' and not 'steering' as described in the manual!
# All values should be sensible for their type, including lists being lists.
# See the SCR manual or http://xed.ch/help/torcs.html for details.
#
# If you just run the snakeoil.py base library itself it will implement a
# serviceable client with a demonstration drive function that is
# sufficient for getting around most tracks.
# Try `snakeoil.py --help` to get started.
#
# ============================================================
# snakeoil3_v2.py — WORKING COPY (experimental + recording)
# Safe baseline (read-only reference): snakeoil3_v1.py  (exp-18)
# Original reference (never modified): snakeoil3_gym.py
# Full experiment history:             CHANGELOG.md
# Accumulated driving data:            lap_data.csv
# Per-lap summary:                     lap_summary.csv
# Offline analysis tool:               find_corners.py
# Experiment reports:                  reports/
#
# Workflow:
#   1. Run snakeoil3_v1.py to confirm baseline is still clean.
#   2. Make ONE change in drive_example() below for the next experiment.
#      Update EXP_TAG to the experiment name (e.g. "exp-19").
#   3. Run this file — telemetry writes to lap_data.csv / lap_summary.csv
#      automatically; data accumulates across all runs.
#   4. Record result in CHANGELOG.md (version, change, before/after metrics, kept?).
#   5. If clean: copy drive_example back to snakeoil3_v1.py. Reset EXP_TAG.
#   6. If crash: revert drive_example to v1 baseline. Reset EXP_TAG.
# ============================================================

# for Python3-based torcs python robot client
import socket
import sys
import getopt
import os
import time
import csv
import uuid
import datetime
import hashlib
import math
PI= 3.14159265359

# ---------------------------------------------------------------------------
# EXPERIMENT LABEL — change before each new experiment run.
# Appears in every row of lap_data.csv and lap_summary.csv.
# Example: "exp-19-margin089"
EXP_TAG = "exp-44-widercone-5to16"
# ---------------------------------------------------------------------------

data_size = 2**17

# Initialize help messages
ophelp=  'Options:\n'
ophelp+= ' --host, -H <host>    TORCS server host. [localhost]\n'
ophelp+= ' --port, -p <port>    TORCS port. [3001]\n'
ophelp+= ' --id, -i <id>        ID for server. [SCR]\n'
ophelp+= ' --steps, -m <#>      Maximum simulation steps. 1 sec ~ 50 steps. [100000]\n'
ophelp+= ' --episodes, -e <#>   Maximum learning episodes. [1]\n'
ophelp+= ' --track, -t <track>  Your name for this track. Used for learning. [unknown]\n'
ophelp+= ' --stage, -s <#>      0=warm up, 1=qualifying, 2=race, 3=unknown. [3]\n'
ophelp+= ' --debug, -d          Output full telemetry.\n'
ophelp+= ' --help, -h           Show this help.\n'
ophelp+= ' --version, -v        Show current version.'
usage= 'Usage: %s [ophelp [optargs]] \n' % sys.argv[0]
usage= usage + ophelp
version= "20130505-2"

def clip(v,lo,hi):
    if v<lo: return lo
    elif v>hi: return hi
    else: return v

def bargraph(x,mn,mx,w,c='X'):
    '''Draws a simple asciiart bar graph. Very handy for
    visualizing what's going on with the data.
    x= Value from sensor, mn= minimum plottable value,
    mx= maximum plottable value, w= width of plot in chars,
    c= the character to plot with.'''
    if not w: return '' # No width!
    if x<mn: x= mn      # Clip to bounds.
    if x>mx: x= mx      # Clip to bounds.
    tx= mx-mn # Total real units possible to show on graph.
    if tx<=0: return 'backwards' # Stupid bounds.
    upw= tx/float(w) # X Units per output char width.
    if upw<=0: return 'what?' # Don't let this happen.
    negpu, pospu, negnonpu, posnonpu= 0,0,0,0
    if mn < 0: # Then there is a negative part to graph.
        if x < 0: # And the plot is on the negative side.
            negpu= -x + min(0,mx)
            negnonpu= -mn + x
        else: # Plot is on pos. Neg side is empty.
            negnonpu= -mn + min(0,mx) # But still show some empty neg.
    if mx > 0: # There is a positive part to the graph
        if x > 0: # And the plot is on the positive side.
            pospu= x - max(0,mn)
            posnonpu= mx - x
        else: # Plot is on neg. Pos side is empty.
            posnonpu= mx - max(0,mn) # But still show some empty pos.
    nnc= int(negnonpu/upw)*'-'
    npc= int(negpu/upw)*c
    ppc= int(pospu/upw)*c
    pnc= int(posnonpu/upw)*'_'
    return '[%s]' % (nnc+npc+ppc+pnc)

class Client():
    def __init__(self,H=None,p=None,i=None,e=None,t=None,s=None,d=None,vision=False):
        # If you don't like the option defaults,  change them here.
        self.vision = vision

        self.host= 'localhost'
        self.port= 3001
        self.sid= 'SCR'
        self.maxEpisodes=1 # "Maximum number of learning episodes to perform"
        self.trackname= 'unknown'
        self.stage= 3 # 0=Warm-up, 1=Qualifying 2=Race, 3=unknown <Default=3>
        self.debug= False
        self.maxSteps= 100000  # 50steps/second
        self.parse_the_command_line()
        if H: self.host= H
        if p: self.port= p
        if i: self.sid= i
        if e: self.maxEpisodes= e
        if t: self.trackname= t
        if s: self.stage= s
        if d: self.debug= d
        self.S= ServerState()
        self.R= DriverAction()
        self.setup_connection()

    def setup_connection(self):
        # == Set Up UDP Socket ==
        try:
            self.so= socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except socket.error as emsg:
            print('Error: Could not create socket...')
            sys.exit(-1)
        # == Initialize Connection To Server ==
        self.so.settimeout(1)

        n_fail = 5
        while True:
            # This string establishes track sensor angles! You can customize them.
            #a= "-90 -75 -60 -45 -30 -20 -15 -10 -5 0 5 10 15 20 30 45 60 75 90"
            # xed- Going to try something a bit more aggressive...
            a= "-45 -19 -12 -7 -4 -2.5 -1.7 -1 -.5 0 .5 1 1.7 2.5 4 7 12 19 45"

            initmsg='%s(init %s)' % (self.sid,a)

            try:
                self.so.sendto(initmsg.encode(), (self.host, self.port))
            except socket.error as emsg:
                sys.exit(-1)
            sockdata= str()
            try:
                sockdata,addr= self.so.recvfrom(data_size)
                sockdata = sockdata.decode('utf-8')
            except socket.error as emsg:
                print("Waiting for server on %d............" % self.port)
                print("Count Down : " + str(n_fail))
                if n_fail < 0:
                    print("relaunch torcs")
                    os.system('pkill torcs')
                    time.sleep(1.0)
                    if self.vision is False:
                        os.system('torcs -nofuel -nodamage -nolaptime &')
                    else:
                        os.system('torcs -nofuel -nodamage -nolaptime -vision &')

                    time.sleep(1.0)
                    os.system('sh autostart.sh')
                    n_fail = 5
                n_fail -= 1

            identify = '***identified***'
            if identify in sockdata:
                print("Client connected on %d.............." % self.port)
                break

    def parse_the_command_line(self):
        try:
            (opts, args) = getopt.getopt(sys.argv[1:], 'H:p:i:m:e:t:s:dhv',
                       ['host=','port=','id=','steps=',
                        'episodes=','track=','stage=',
                        'debug','help','version'])
        except getopt.error as why:
            print('getopt error: %s\n%s' % (why, usage))
            sys.exit(-1)
        try:
            for opt in opts:
                if opt[0] == '-h' or opt[0] == '--help':
                    print(usage)
                    sys.exit(0)
                if opt[0] == '-d' or opt[0] == '--debug':
                    self.debug= True
                if opt[0] == '-H' or opt[0] == '--host':
                    self.host= opt[1]
                if opt[0] == '-i' or opt[0] == '--id':
                    self.sid= opt[1]
                if opt[0] == '-t' or opt[0] == '--track':
                    self.trackname= opt[1]
                if opt[0] == '-s' or opt[0] == '--stage':
                    self.stage= int(opt[1])
                if opt[0] == '-p' or opt[0] == '--port':
                    self.port= int(opt[1])
                if opt[0] == '-e' or opt[0] == '--episodes':
                    self.maxEpisodes= int(opt[1])
                if opt[0] == '-m' or opt[0] == '--steps':
                    self.maxSteps= int(opt[1])
                if opt[0] == '-v' or opt[0] == '--version':
                    print('%s %s' % (sys.argv[0], version))
                    sys.exit(0)
        except ValueError as why:
            print('Bad parameter \'%s\' for option %s: %s\n%s' % (
                                       opt[1], opt[0], why, usage))
            sys.exit(-1)
        if len(args) > 0:
            print('Superflous input? %s\n%s' % (', '.join(args), usage))
            sys.exit(-1)

    def get_servers_input(self):
        '''Server's input is stored in a ServerState object'''
        if not self.so: return
        sockdata= str()

        while True:
            try:
                # Receive server data
                sockdata,addr= self.so.recvfrom(data_size)
                sockdata = sockdata.decode('utf-8')
            except socket.error as emsg:
                print('.', end=' ')
                #print "Waiting for data on %d.............." % self.port
            if '***identified***' in sockdata:
                print("Client connected on %d.............." % self.port)
                continue
            elif '***shutdown***' in sockdata:
                print((("Server has stopped the race on %d. "+
                        "You were in %d place.") %
                        (self.port,self.S.d['racePos'])))
                self.shutdown()
                return
            elif '***restart***' in sockdata:
                # What do I do here?
                print("Server has restarted the race on %d." % self.port)
                # I haven't actually caught the server doing this.
                self.shutdown()
                return
            elif not sockdata: # Empty?
                continue       # Try again.
            else:
                self.S.parse_server_str(sockdata)
                if self.debug:
                    sys.stderr.write("\x1b[2J\x1b[H") # Clear for steady output.
                    print(self.S)
                break # Can now return from this function.

    def respond_to_server(self):
        if not self.so: return
        try:
            message = repr(self.R)
            self.so.sendto(message.encode(), (self.host, self.port))
        except socket.error as emsg:
            print("Error sending to server: %s Message %s" % (emsg[1],str(emsg[0])))
            sys.exit(-1)
        if self.debug: print(self.R.fancyout())
        # Or use this for plain output:
        #if self.debug: print self.R

    def shutdown(self):
        if not self.so: return
        print(("Race terminated or %d steps elapsed. Shutting down %d."
               % (self.maxSteps,self.port)))
        self.so.close()
        self.so = None
        #sys.exit() # No need for this really.

class ServerState():
    '''What the server is reporting right now.'''
    def __init__(self):
        self.servstr= str()
        self.d= dict()

    def parse_server_str(self, server_string):
        '''Parse the server string.'''
        self.servstr= server_string.strip()[:-1]
        sslisted= self.servstr.strip().lstrip('(').rstrip(')').split(')(')
        for i in sslisted:
            w= i.split(' ')
            self.d[w[0]]= destringify(w[1:])

    def __repr__(self):
        # Comment the next line for raw output:
        return self.fancyout()
        # -------------------------------------
        out= str()
        for k in sorted(self.d):
            strout= str(self.d[k])
            if type(self.d[k]) is list:
                strlist= [str(i) for i in self.d[k]]
                strout= ', '.join(strlist)
            out+= "%s: %s\n" % (k,strout)
        return out

    def fancyout(self):
        '''Specialty output for useful ServerState monitoring.'''
        out= str()
        sensors= [ # Select the ones you want in the order you want them.
        #'curLapTime',
        #'lastLapTime',
        'stucktimer',
        #'damage',
        #'focus',
        'fuel',
        #'gear',
        'distRaced',
        'distFromStart',
        #'racePos',
        'opponents',
        'wheelSpinVel',
        'z',
        'speedZ',
        'speedY',
        'speedX',
        'targetSpeed',
        'rpm',
        'skid',
        'slip',
        'track',
        'trackPos',
        'angle',
        ]

        #for k in sorted(self.d): # Use this to get all sensors.
        for k in sensors:
            if type(self.d.get(k)) is list: # Handle list type data.
                if k == 'track': # Nice display for track sensors.
                    strout= str()
                 #  for tsensor in self.d['track']:
                 #      if   tsensor >180: oc= '|'
                 #      elif tsensor > 80: oc= ';'
                 #      elif tsensor > 60: oc= ','
                 #      elif tsensor > 39: oc= '.'
                 #      #elif tsensor > 13: oc= chr(int(tsensor)+65-13)
                 #      elif tsensor > 13: oc= chr(int(tsensor)+97-13)
                 #      elif tsensor >  3: oc= chr(int(tsensor)+48-3)
                 #      else: oc= '_'
                 #      strout+= oc
                 #  strout= ' -> '+strout[:9] +' ' + strout[9] + ' ' + strout[10:]+' <-'
                    raw_tsens= ['%.1f'%x for x in self.d['track']]
                    strout+= ' '.join(raw_tsens[:9])+'_'+raw_tsens[9]+'_'+' '.join(raw_tsens[10:])
                elif k == 'opponents': # Nice display for opponent sensors.
                    strout= str()
                    for osensor in self.d['opponents']:
                        if   osensor >190: oc= '_'
                        elif osensor > 90: oc= '.'
                        elif osensor > 39: oc= chr(int(osensor/2)+97-19)
                        elif osensor > 13: oc= chr(int(osensor)+65-13)
                        elif osensor >  3: oc= chr(int(osensor)+48-3)
                        else: oc= '?'
                        strout+= oc
                    strout= ' -> '+strout[:18] + ' ' + strout[18:]+' <-'
                else:
                    strlist= [str(i) for i in self.d[k]]
                    strout= ', '.join(strlist)
            else: # Not a list type of value.
                if k == 'gear': # This is redundant now since it's part of RPM.
                    gs= '_._._._._._._._._'
                    p= int(self.d['gear']) * 2 + 2  # Position
                    l= '%d'%self.d['gear'] # Label
                    if l=='-1': l= 'R'
                    if l=='0':  l= 'N'
                    strout= gs[:p]+ '(%s)'%l + gs[p+3:]
                elif k == 'damage':
                    strout= '%6.0f %s' % (self.d[k], bargraph(self.d[k],0,10000,50,'~'))
                elif k == 'fuel':
                    strout= '%6.0f %s' % (self.d[k], bargraph(self.d[k],0,100,50,'f'))
                elif k == 'speedX':
                    cx= 'X'
                    if self.d[k]<0: cx= 'R'
                    strout= '%6.1f %s' % (self.d[k], bargraph(self.d[k],-30,300,50,cx))
                elif k == 'speedY': # This gets reversed for display to make sense.
                    strout= '%6.1f %s' % (self.d[k], bargraph(self.d[k]*-1,-25,25,50,'Y'))
                elif k == 'speedZ':
                    strout= '%6.1f %s' % (self.d[k], bargraph(self.d[k],-13,13,50,'Z'))
                elif k == 'z':
                    strout= '%6.3f %s' % (self.d[k], bargraph(self.d[k],.3,.5,50,'z'))
                elif k == 'trackPos': # This gets reversed for display to make sense.
                    cx='<'
                    if self.d[k]<0: cx= '>'
                    strout= '%6.3f %s' % (self.d[k], bargraph(self.d[k]*-1,-1,1,50,cx))
                elif k == 'stucktimer':
                    if self.d[k]:
                        strout= '%3d %s' % (self.d[k], bargraph(self.d[k],0,300,50,"'"))
                    else: strout= 'Not stuck!'
                elif k == 'rpm':
                    g= self.d['gear']
                    if g < 0:
                        g= 'R'
                    else:
                        g= '%1d'% g
                    strout= bargraph(self.d[k],0,10000,50,g)
                elif k == 'angle':
                    asyms= [
                          "  !  ", ".|'  ", "./'  ", "_.-  ", ".--  ", "..-  ",
                          "---  ", ".__  ", "-._  ", "'-.  ", "'\.  ", "'|.  ",
                          "  |  ", "  .|'", "  ./'", "  .-'", "  _.-", "  __.",
                          "  ---", "  --.", "  -._", "  -..", "  '\.", "  '|."  ]
                    rad= self.d[k]
                    deg= int(rad*180/PI)
                    symno= int(.5+ (rad+PI) / (PI/12) )
                    symno= symno % (len(asyms)-1)
                    strout= '%5.2f %3d (%s)' % (rad,deg,asyms[symno])
                elif k == 'skid': # A sensible interpretation of wheel spin.
                    frontwheelradpersec= self.d['wheelSpinVel'][0]
                    skid= 0
                    if frontwheelradpersec:
                        skid= .5555555555*self.d['speedX']/frontwheelradpersec - .66124
                    strout= bargraph(skid,-.05,.4,50,'*')
                elif k == 'slip': # A sensible interpretation of wheel spin.
                    frontwheelradpersec= self.d['wheelSpinVel'][0]
                    slip= 0
                    if frontwheelradpersec:
                        slip= ((self.d['wheelSpinVel'][2]+self.d['wheelSpinVel'][3]) -
                              (self.d['wheelSpinVel'][0]+self.d['wheelSpinVel'][1]))
                    strout= bargraph(slip,-5,150,50,'@')
                else:
                    strout= str(self.d[k])
            out+= "%s: %s\n" % (k,strout)
        return out

class DriverAction():
    '''What the driver is intending to do (i.e. send to the server).
    Composes something like this for the server:
    (accel 1)(brake 0)(gear 1)(steer 0)(clutch 0)(focus 0)(meta 0) or
    (accel 1)(brake 0)(gear 1)(steer 0)(clutch 0)(focus -90 -45 0 45 90)(meta 0)'''
    def __init__(self):
       self.actionstr= str()
       # "d" is for data dictionary.
       self.d= { 'accel':0.2,
                   'brake':0,
                  'clutch':0,
                    'gear':1,
                   'steer':0,
                   'focus':[-90,-45,0,45,90],
                    'meta':0
                    }

    def clip_to_limits(self):
        """There pretty much is never a reason to send the server
        something like (steer 9483.323). This comes up all the time
        and it's probably just more sensible to always clip it than to
        worry about when to. The "clip" command is still a snakeoil
        utility function, but it should be used only for non standard
        things or non obvious limits (limit the steering to the left,
        for example). For normal limits, simply don't worry about it."""
        self.d['steer']= clip(self.d['steer'], -1, 1)
        self.d['brake']= clip(self.d['brake'], 0, 1)
        self.d['accel']= clip(self.d['accel'], 0, 1)
        self.d['clutch']= clip(self.d['clutch'], 0, 1)
        if self.d['gear'] not in [-1, 0, 1, 2, 3, 4, 5, 6, 7]:
            self.d['gear']= 0
        if self.d['meta'] not in [0,1]:
            self.d['meta']= 0
        if type(self.d['focus']) is not list or min(self.d['focus'])<-180 or max(self.d['focus'])>180:
            self.d['focus']= 0

    def __repr__(self):
        self.clip_to_limits()
        out= str()
        for k in self.d:
            out+= '('+k+' '
            v= self.d[k]
            if not type(v) is list:
                out+= '%.3f' % v
            else:
                out+= ' '.join([str(x) for x in v])
            out+= ')'
        return out
        return out+'\n'

    def fancyout(self):
        '''Specialty output for useful monitoring of bot's effectors.'''
        out= str()
        od= self.d.copy()
        od.pop('gear','') # Not interesting.
        od.pop('meta','') # Not interesting.
        od.pop('focus','') # Not interesting. Yet.
        for k in sorted(od):
            if k == 'clutch' or k == 'brake' or k == 'accel':
                strout=''
                strout= '%6.3f %s' % (od[k], bargraph(od[k],0,1,50,k[0].upper()))
            elif k == 'steer': # Reverse the graph to make sense.
                strout= '%6.3f %s' % (od[k], bargraph(od[k]*-1,-1,1,50,'S'))
            else:
                strout= str(od[k])
            out+= "%s: %s\n" % (k,strout)
        return out

# == Misc Utility Functions
def destringify(s):
    '''makes a string into a value or a list of strings into a list of
    values (if possible)'''
    if not s: return s
    if type(s) is str:
        try:
            return float(s)
        except ValueError:
            print("Could not find a value in %s" % s)
            return s
    elif type(s) is list:
        if len(s) < 2:
            return destringify(s[0])
        else:
            return [destringify(i) for i in s]

# ===========================================================================
# Telemetry recorder
# ===========================================================================
# LOGGING OVERHEAD NOTE
# ---------------------
# At ~50 Hz each tick calls:
#   - datetime.datetime.utcnow()  : ~1 µs
#   - time.monotonic()            : ~0.1 µs
#   - csv.writer.writerow()       : ~5–15 µs (formatting + buffered I/O)
#   - f.flush()                   : ~5–50 µs (OS syscall; varies with disk)
# Total per tick: ~10–70 µs, well under the ~20 ms tick budget (~0.1–0.4%).
# flush() per row guarantees no data loss on crash at the cost of extra
# syscalls; on a spinning disk this could reach ~0.5 ms/tick (~2.5%
# overhead). On an SSD or RAM-backed filesystem it is negligible.
# The sha256 hash and header checks happen once at startup only.
# ===========================================================================

# ---------------------------------------------------------------------------
# Sensor angle list (hardcoded in setup_connection — must match if changed).
# Angles: -45 -19 -12 -7 -4 -2.5 -1.7 -1 -0.5  0  0.5  1  1.7  2.5  4  7  12  19  45
# Index:    0   1   2  3  4   5    6   7    8   9   10  11   12   13 14 15  16  17  18
# Index 9 = 0° = dead ahead.  This is the FORWARD_TRACK_INDEX used below.
# ---------------------------------------------------------------------------
_SENSOR_ANGLES = [-45,-19,-12,-7,-4,-2.5,-1.7,-1,-.5,0,.5,1,1.7,2.5,4,7,12,19,45]
FORWARD_TRACK_INDEX = _SENSOR_ANGLES.index(0)   # must be 9

assert FORWARD_TRACK_INDEX == 9, (
    "Forward sensor index mismatch — check the angle list in setup_connection")


def _hash_self():
    """SHA-256 of this script file.  Called once at startup."""
    try:
        with open(__file__, 'rb') as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except Exception:
        return ''


def _valid_track_readings(track_list):
    """Return finite, positive track distance readings from the 19-element list.

    TORCS reports -1 for sensors that point outside the track boundary or
    behind the car.  We exclude any value that is <= 0 or non-finite.
    Units: metres (TORCS track sensors report distance in metres).
    """
    return [v for v in track_list
            if isinstance(v, (int, float)) and math.isfinite(v) and v > 0]


class Recorder:
    """Append-only telemetry logger producing two CSV files.

    Analogy: open a lab notebook, label the run/lap, record each moment,
    summarise a finished lap page, then save and close the book.

      lap_data.csv    — one row per simulator step (~50 Hz); never truncated.
      lap_summary.csv — one row per completed lap + one row for any
                        partial/interrupted lap on normal exit or Ctrl+C.

    Both files accumulate across all runs.  A new unique run_id is minted
    each time the process starts.

    LAP DETECTION — design and limits
    ----------------------------------
    The SCR protocol does NOT transmit a lap counter in its sensor string.
    S.get('lap', ...) would always return the default — it is not a real
    sensor.  Lap transitions are therefore detected from distFromStart:

      A finish-line crossing is confirmed when ALL of:
        1. distFromStart drops by more than LAP_WRAP_THRESHOLD metres
           relative to the previous step (the counter wraps near track end).
        2. The new distFromStart value is < LAP_NEAR_START_MAX metres
           (the car is genuinely near the start, not just a sensor glitch).
        3. distRaced has increased monotonically — the car was moving
           forward, not reversing or sitting still.
        4. curLapTime has been running for at least LAP_MIN_TIME seconds
           (rules out spurious wrap on the very first step and sim resets).

    Known limits:
      - A very short circuit (< LAP_WRAP_THRESHOLD) could cause a missed
        crossing.  The threshold is 200 m by default.
      - A hard crash that teleports the car back near the start is
        indistinguishable from a lap finish.  The curLapTime guard (30 s
        minimum) mitigates but does not eliminate this.
      - Rows before the first confirmed crossing are labelled 'warmup'.
      - Rows within a lap that has not yet crossed the line are 'partial'.
      - After a confirmed crossing the new lap's rows are labelled 'flying'.

    EPISODE DETECTION
    -----------------
    When the simulator resets (***restart*** or a new episode starts), the
    existing client loop ends.  A server-initiated shutdown is caught by
    the existing shutdown handler.  If distRaced drops significantly while
    curLapTime is near zero, we treat it as a new episode even within the
    same process: a new episode_id is assigned and accumulator state resets.
    """

    LAP_DATA_PATH    = 'lap_data.csv.gz'   # gzip-compressed; read with gzip.open()
    LAP_SUMMARY_PATH = 'lap_summary.csv'

    # Finish-line detection thresholds (see docstring above)
    LAP_WRAP_THRESHOLD  = 200.0   # m  — minimum drop in distFromStart to count as wrap
    LAP_NEAR_START_MAX  = 150.0   # m  — new distFromStart must be below this
    LAP_MIN_TIME        = 30.0    # s  — curLapTime must have run at least this long
    EPISODE_RESET_DIST  = 500.0   # m  — distRaced drop this large = simulator reset

    LAP_DATA_COLS = [
        'run_id', 'experiment_id',
        'step', 'elapsed_time_s',
        'distFromStart', 'distRaced', 'curLapTime', 'lastLapTime',
        'speedX', 'trackPos', 'angle',
        'steer', 'accel', 'brake', 'gear',
        'forward_track', 'min_valid_track',
        'damage',
    ]
    # Columns removed during cleanup (still available in lap_summary.csv):
    #   code_sha256  — 64 chars/row; linked via run_id in lap_summary
    #   track_id     — always 'unknown'
    #   episode_id   — derivable from run_id
    #   utc_timestamp — redundant with elapsed_time_s + run_id
    #   lap_id       — always 1 per session
    #   lap_status   — derivable from distRaced progression

    LAP_SUMMARY_COLS = [
        'run_id', 'episode_id', 'lap_id', 'experiment_id', 'code_sha256',
        'status', 'lap_time', 'timing_note',
        'damage_start', 'damage_end',
        'max_speed', 'completion_reason',
    ]

    def __init__(self, exp_tag, track_id=''):
        self.exp_tag  = exp_tag
        self.track_id = track_id
        self.run_id   = (datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')
                         + 'Z_' + uuid.uuid4().hex[:8])
        self.code_sha = _hash_self()
        self._t0      = time.monotonic()
        self._step    = 0

        # Episode state
        self._episode_id      = self._new_id('ep')
        self._episode_dist_r  = None   # first distRaced seen this episode

        # Lap state
        self._lap_id          = 1
        self._lap_status      = 'warmup'   # warmup → partial → flying
        self._lap_confirmed   = False       # True once we've seen one full lap
        self._prev_dist       = None        # distFromStart last step
        self._prev_dist_r     = None        # distRaced last step
        self._lap_start_dist_r= None        # distRaced at start of this lap
        self._damage_start    = None
        self._max_speed       = 0.0
        self._summary_written = False       # guard against double summary write

        # Open files once; check / write headers
        self._data_fh    = self._open_and_check(
            self.LAP_DATA_PATH, self.LAP_DATA_COLS)
        self._summary_fh = self._open_and_check(
            self.LAP_SUMMARY_PATH, self.LAP_SUMMARY_COLS)
        self._data_w    = csv.DictWriter(
            self._data_fh,    fieldnames=self.LAP_DATA_COLS,    extrasaction='ignore')
        self._summary_w = csv.DictWriter(
            self._summary_fh, fieldnames=self.LAP_SUMMARY_COLS, extrasaction='ignore')

        print('[Recorder] run_id       = %s' % self.run_id)
        print('[Recorder] experiment_id= %s' % self.exp_tag)
        print('[Recorder] code_sha256  = %s...' % self.code_sha[:16])
        print('[Recorder] lap_data     -> %s' % self.LAP_DATA_PATH)
        print('[Recorder] lap_summary  -> %s' % self.LAP_SUMMARY_PATH)
        print('[Recorder] forward sensor index %d (0°)' % FORWARD_TRACK_INDEX)

    # ------------------------------------------------------------------
    @staticmethod
    def _new_id(prefix):
        return '%s_%s' % (prefix, uuid.uuid4().hex[:8])

    # ------------------------------------------------------------------
    @staticmethod
    def _open_and_check(path, expected_cols):
        """Open path in append mode (gzip for .gz paths, plain text otherwise).
        If the file has content, read its header and abort if incompatible.
        Returns the open file handle positioned at EOF."""
        import gzip as _gzip
        is_gz  = path.endswith('.gz')
        is_new = (not os.path.exists(path)) or os.path.getsize(path) == 0

        if is_gz:
            # gzip append: open in 'ab' binary mode, wrap with GzipFile.
            # Each open() creates a new gzip stream appended to the file;
            # readers concatenate streams automatically (RFC 1952 §2.2).
            raw = open(path, 'ab')
            fh  = _gzip.open(raw, 'wt', encoding='utf-8', newline='')
        else:
            fh = open(path, 'a', newline='', encoding='utf-8')

        if is_new:
            w = csv.writer(fh)
            w.writerow(expected_cols)
            fh.flush()
            print('[Recorder] created %s with header' % path)
        else:
            # Read existing header to check compatibility
            if is_gz:
                with _gzip.open(path, 'rt', encoding='utf-8') as rh:
                    existing = next(csv.reader(rh), None)
            else:
                with open(path, 'r', newline='', encoding='utf-8') as rh:
                    existing = next(csv.reader(rh), None)
            if existing != expected_cols:
                fh.close()
                print('\n[Recorder] INCOMPATIBLE HEADER in %s' % path)
                print('  Found    : %s' % existing)
                print('  Required : %s' % expected_cols)
                print('  Rename or delete the old file, or update the column list.')
                print('  The existing file has NOT been modified.')
                sys.exit(1)
            print('[Recorder] appending to existing %s' % path)
        return fh

    # ------------------------------------------------------------------
    def record_step(self, S, R):
        """Record one simulator step.

        Call AFTER controls are computed and BEFORE they are sent.
        S — the server-state dict (c.S.d).
        R — the driver-action dict (c.R.d).
        """
        self._step += 1
        now_utc   = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'
        elapsed   = round(time.monotonic() - self._t0, 4)

        # ---- Read sensors (never invent; blank when unavailable) ----
        dist      = S.get('distFromStart', '')
        dist_r    = S.get('distRaced',     '')
        cur_t     = S.get('curLapTime',    '')
        last_t    = S.get('lastLapTime',   '')
        speed     = S.get('speedX',        '')
        track_pos = S.get('trackPos',      '')
        angle     = S.get('angle',         '')
        damage    = S.get('damage',        '')
        track     = S.get('track',         [])

        # ---- Derived sensor values ----
        # forward_track: index 9 (0° dead-ahead), validated positive+finite
        if track and len(track) > FORWARD_TRACK_INDEX:
            fwd_raw = track[FORWARD_TRACK_INDEX]
            forward_track = (round(fwd_raw, 3)
                             if (isinstance(fwd_raw, (int, float))
                                 and math.isfinite(fwd_raw) and fwd_raw > 0)
                             else '')
        else:
            forward_track = ''

        # min_valid_track: minimum of all valid (positive, finite) readings
        valid = _valid_track_readings(track)
        min_valid_track = round(min(valid), 3) if valid else ''

        # ---- Episode reset detection ----
        # If distRaced drops substantially vs last step, treat as new episode.
        if (self._prev_dist_r is not None
                and isinstance(dist_r, (int, float))
                and isinstance(self._prev_dist_r, (int, float))
                and self._prev_dist_r - dist_r > self.EPISODE_RESET_DIST):
            self._on_episode_reset(S)

        # Initialise episode_dist_r on first valid reading
        if self._episode_dist_r is None and isinstance(dist_r, (int, float)):
            self._episode_dist_r  = dist_r
            self._lap_start_dist_r = dist_r

        # ---- Lap detection (finish-line crossing) ----
        if (self._prev_dist is not None
                and isinstance(dist, (int, float))
                and isinstance(self._prev_dist, (int, float))):
            drop       = self._prev_dist - dist
            fwd_moved  = (isinstance(dist_r, (int, float))
                          and isinstance(self._prev_dist_r, (int, float))
                          and dist_r > self._prev_dist_r)
            long_enough = (isinstance(cur_t, (int, float))
                           and cur_t >= self.LAP_MIN_TIME)
            near_start  = (isinstance(dist, (int, float))
                           and dist < self.LAP_NEAR_START_MAX)

            if (drop > self.LAP_WRAP_THRESHOLD
                    and near_start and fwd_moved and long_enough):
                self._on_lap_finish(S, last_t, dist_r, damage)

        # ---- Update lap status ----
        if self._lap_status == 'warmup' and self._lap_confirmed:
            self._lap_status = 'flying'
        elif self._lap_status == 'warmup' and self._step > 1:
            self._lap_status = 'partial'

        # ---- Track speed for summary ----
        if isinstance(speed, (int, float)) and speed > self._max_speed:
            self._max_speed = speed

        # ---- Initialise damage baseline ----
        if self._damage_start is None and isinstance(damage, (int, float)):
            self._damage_start = damage

        # ---- Write data row ----
        row = {
            'run_id':          self.run_id,
            'episode_id':      self._episode_id,
            'experiment_id':   self.exp_tag,
            'step':            self._step,
            'utc_timestamp':   now_utc,
            'elapsed_time_s':  elapsed,
            'lap_id':          self._lap_id,
            'lap_status':      self._lap_status,
            'distFromStart':   (round(dist, 3)
                                if isinstance(dist, (int, float)) else ''),
            'distRaced':       (round(dist_r, 3)
                                if isinstance(dist_r, (int, float)) else ''),
            'curLapTime':      (round(cur_t, 3)
                                if isinstance(cur_t, (int, float)) else ''),
            'lastLapTime':     (round(last_t, 3)
                                if isinstance(last_t, (int, float)) else ''),
            'speedX':          (round(speed, 3)
                                if isinstance(speed, (int, float)) else ''),
            'trackPos':        (round(track_pos, 6)
                                if isinstance(track_pos, (int, float)) else ''),
            'angle':           (round(angle, 6)
                                if isinstance(angle, (int, float)) else ''),
            'steer':           (round(R.get('steer', ''), 6)
                                if isinstance(R.get('steer'), (int, float)) else ''),
            'accel':           (round(R.get('accel', ''), 4)
                                if isinstance(R.get('accel'), (int, float)) else ''),
            'brake':           (round(R.get('brake', ''), 4)
                                if isinstance(R.get('brake'), (int, float)) else ''),
            'gear':            R.get('gear', ''),
            'forward_track':   forward_track,
            'min_valid_track': min_valid_track,
            'damage':          (round(damage, 1)
                                if isinstance(damage, (int, float)) else ''),
        }
        self._data_w.writerow(row)
        self._data_fh.flush()   # flush every row — guarantees data survives crash

        # ---- Update prev values for next step ----
        if isinstance(dist,   (int, float)): self._prev_dist   = dist
        if isinstance(dist_r, (int, float)): self._prev_dist_r = dist_r

    # ------------------------------------------------------------------
    def _on_lap_finish(self, S, last_t, dist_r, damage):
        """Called when a finish-line crossing is confirmed."""
        # Reconcile lap time: use lastLapTime from the simulator when it
        # becomes available (it is the authoritative timing).
        if isinstance(last_t, (int, float)) and last_t > 0:
            lap_time   = round(last_t, 3)
            timing_note = 'simulator_lastLapTime'
        else:
            lap_time    = ''
            timing_note = 'unavailable — lastLapTime missing or zero'

        damage_end = (round(damage, 1)
                      if isinstance(damage, (int, float)) else '')

        if not self._summary_written:
            self._write_summary(
                status            = 'completed',
                lap_time          = lap_time,
                timing_note       = timing_note,
                damage_end        = damage_end,
                completion_reason = 'finish_line_crossing',
            )
            self._summary_written = True

        # Reset for the next lap
        self._lap_id         += 1
        self._lap_status      = 'flying'
        self._lap_confirmed   = True
        self._summary_written = False
        self._damage_start    = (round(damage, 1)
                                 if isinstance(damage, (int, float)) else None)
        self._max_speed       = 0.0
        self._lap_start_dist_r = dist_r

    # ------------------------------------------------------------------
    def _on_episode_reset(self, S):
        """Called when a simulator reset is detected mid-run."""
        print('[Recorder] episode reset detected — new episode_id')
        self._write_summary(
            status            = 'interrupted',
            lap_time          = '',
            timing_note       = 'episode_reset_detected',
            damage_end        = (round(S.get('damage', ''), 1)
                                 if isinstance(S.get('damage'), (int, float))
                                 else ''),
            completion_reason = 'simulator_reset',
        )
        self._episode_id      = self._new_id('ep')
        self._episode_dist_r  = None
        self._lap_id          = 1
        self._lap_status      = 'warmup'
        self._lap_confirmed   = False
        self._prev_dist       = None
        self._prev_dist_r     = None
        self._lap_start_dist_r = None
        self._damage_start    = None
        self._max_speed       = 0.0
        self._summary_written = False

    # ------------------------------------------------------------------
    def close_partial(self, S, reason='user_interrupt'):
        """Write a partial-lap summary and close files.

        Call from the finally block so every normal exit or Ctrl+C produces
        a summary row.  If the process is killed with SIGKILL the finally
        block does NOT run; already-flushed lap_data.csv rows survive but
        no final partial summary is written — this is unavoidable.
        """
        if not self._summary_written:
            damage = S.get('damage', '') if S else ''
            damage_end = (round(damage, 1)
                          if isinstance(damage, (int, float)) else '')
            self._write_summary(
                status            = 'partial',
                lap_time          = '',
                timing_note       = 'partial — lap not completed',
                damage_end        = damage_end,
                completion_reason = reason,
            )
        self._data_fh.flush()
        self._summary_fh.flush()
        self._data_fh.close()
        self._summary_fh.close()

    # ------------------------------------------------------------------
    def _write_summary(self, status, lap_time, timing_note,
                       damage_end, completion_reason):
        row = {
            'run_id':            self.run_id,
            'episode_id':        self._episode_id,
            'lap_id':            self._lap_id,
            'experiment_id':     self.exp_tag,
            'code_sha256':       self.code_sha,
            'status':            status,
            'lap_time':          lap_time,
            'timing_note':       timing_note,
            'damage_start':      (round(self._damage_start, 1)
                                  if isinstance(self._damage_start, (int, float))
                                  else ''),
            'damage_end':        damage_end,
            'max_speed':         round(self._max_speed, 1),
            'completion_reason': completion_reason,
        }
        self._summary_w.writerow(row)
        self._summary_fh.flush()


# ===========================================================================
# Driver — working copy (exp-18 baseline; tune ONE thing and update EXP_TAG)
# ===========================================================================

def drive_example(c):
    '''Working-copy driver — exp-44 (restored).  See CHANGELOG.md for history.

    exp-45 was reverted: t[4:17] (±12° cone) stalled mid-lap at 32 s
    (same mode as exp-42 decel_g=18). ±12° sensors over-read clearance on
    a tight off-cap section, caused emergency braking from 189 km/h → zero,
    yaw-recovery locked the car. Reverted to exp-44 proven cone t[5:16].

    exp-44 changes (vs exp-43):
      Widen sensor cone t[6:15] → t[5:16] (±2.5°–±7° vs ±1.7°–±4°).
      On clear straights all sensors read ~200 m so ahead is unchanged.
      On gentle sweepers the wider sensors see further along the driving
      line, raising safe_kmh and target_speed without touching decel_g or
      margin — more straight-line speed with no braking-distance trade-off.
      Zone caps (A/B/C) unchanged — distance-gated so sensor width irrelevant
      at those corners.
      decel_g=17, margin=0.97 unchanged from exp-43.

    exp-43 changes (vs exp-42):
      Revert decel_g 18 → 17: exp-42 stalled mid-lap at 39 s (top speed 189,
      damage 0). decel_g=18 fires brake trigger so late that a brief low-ahead
      reading (kink/apex) causes full emergency braking from 189 km/h → near
      zero; yaw-recovery then locks the car. decel_g=17 was clean in exp-41.
      margin 0.97 KEPT: isolates decel_g as the failure cause.
      Zone caps (A/B/C) unchanged.

    exp-42 changes (vs exp-41):
      decel_g 17 → 18: brake trigger fires even later → more time at full
      throttle on straights.
      margin 0.95 → 0.97: target speed nearly at sensor ceiling.
      Zone caps (A/B/C) unchanged — still guard all three problem corners.
      Historical note: decel_g=18 DNF'd in exp-14, but that run had NO zone
      caps and a broken recovery logic. Caps + working recovery make this safe.

    exp-41 changes (vs exp-40):
      decel_g 16 → 17: brake trigger fires later on straights → more time at
      full throttle → higher top speed.
      margin 0.92 → 0.95: target speed chases sensor ceiling more aggressively.
      Both levers raise straight-line speed; zone caps (A/B/C) unchanged and
      still guard the three problem corners.
      Historical note: decel_g=17+margin=0.93 crashed in exp-13/14, but those
      runs had NO zone caps. Caps are what make this combination safe to try.

    exp-40 changes (vs exp-39):
      Raise safety margin 0.89 → 0.92 to push top speed toward 220 km/h.
      All zone caps (A/B/C), sensor, decel_g, and steering unchanged.
      exp-13 ran margin 0.92 (among other changes) and observed 219 km/h;
      this isolates that single lever for clean attribution.

    exp-39 changes (vs exp-38):
      Revert dual-sensor back to wide-cone (exp-37 sensor) — dual sensor was
      too conservative, dropped top speed 209 → 173 km/h and never exited Zone A.
      Restore Zone A/B/C hard caps (proven clean in exp-37, 0 damage, distRaced 3618 m).
      Revert margin 0.94 → 0.89 and ceiling 320 → 250 (caps handle the problem corners;
      higher margin without caps caused crashes in earlier experiments).
      Revert throttle_band 6% → 10% (exp-37 baseline).
      TC threshold reverted to 5 always (exp-37 value).
      Gear 7 KEPT (>175 km/h) — no downside, car has 7 gears.

    exp-39 also fixes the main-loop exhaustion bug:
      After C.get_servers_input() the loop now breaks when C.so is None
      (server sent ***shutdown***).  Previously the loop ran all maxSteps
      after race end, preventing lap completion from being confirmed by the
      recorder (distRaced non-monotonic during reversal caused missed crossing).

    Unchanged from exp-37:
      Zone A steer correction: 2290–2450 m (gain 0.15)
      Zone A cap: 2305–2450 m, 40 km/h
      Zone C cap: 2450–2510 m, 55 km/h
      Zone B cap: 3200–3340 m, 60 km/h
      recovery steer (cap ±0.7), yaw-gate, off-track threshold, decel_g=16

    DO NOT tune speed, brakes, steering or gears in this function
    without updating EXP_TAG and recording the change in CHANGELOG.md.
    '''
    S, R = c.S.d, c.R.d

    # --- Forward clearance (wide-cone, exp-37 sensor) ---
    # Sensor angle map:
    # idx:  0    1    2    3   4    5     6     7    8     9   10    11    12    13   14  15   16   17   18
    # deg: -45 -19  -12   -7  -4  -2.5  -1.7  -1  -0.5   0  +0.5  +1  +1.7  +2.5  +4  +7  +12  +19  +45
    t = S['track']
    ahead = max(max(t[5:16]), 0.0)   # exp-44: ±7° cone (exp-45 t[4:17] reverted)

    # --- Steering ---
    R['steer'] = S['angle'] * 5 / PI
    R['steer'] -= S['trackPos'] * 0.40

    # --- Lookahead braking + proportional throttle ---
    decel_g      = 17.0
    safe_ms      = (2.0 * decel_g * ahead) ** 0.5
    safe_kmh     = safe_ms * 3.6
    target_speed = clip(safe_kmh * 0.97, 10, 250)

    # --- Zone-specific speed caps ---
    # Three corners where the wide-cone sensor over-reads clearance (sweeping curves
    # where off-axis sensors see further than the actual driving line).
    # Caps are applied before the throttle/brake logic via the in_cap flag, which
    # switches to active braking (not just target reduction) so the car reaches the
    # cap speed before entering the danger geometry.
    dist = S.get('distFromStart', 0.0) or 0.0

    # Zone A steer correction — extra centre-pull 100 m before + through Corkscrew
    if 2290.0 <= dist < 2450.0:
        R['steer'] -= S['trackPos'] * 0.15

    in_cap = False
    if 2305.0 <= dist < 2450.0:          # Zone A — Corkscrew apex
        target_speed = min(target_speed, 40.0)
        in_cap = True
    if 2450.0 < dist <= 2510.0:          # Zone C — Corkscrew exit chicane
        target_speed = min(target_speed, 55.0)
        in_cap = True
    if 3200.0 <= dist <= 3340.0:         # Zone B — back-section hairpin
        target_speed = min(target_speed, 60.0)
        in_cap = True

    speed_error = target_speed - S['speedX']

    if S['speedX'] <= target_speed:
        throttle_band = target_speed * 0.10
        R['accel'] = 1.0 if speed_error > throttle_band else clip(speed_error / throttle_band, 0, 1)
        R['brake'] = 0
    elif in_cap:
        # Inside a zone cap: actively brake to the cap target (not just coast).
        R['accel'] = 0
        R['brake'] = clip((S['speedX'] - target_speed) / 35.0, 0, 1)
    elif S['speedX'] <= safe_kmh:
        # Normal lookahead: between target and safe speed — coast.
        R['accel'] = 0
        R['brake'] = 0
    else:
        # Over the lookahead safe speed — brake.
        R['accel'] = 0
        R['brake'] = clip((S['speedX'] - safe_kmh) / 35.0, 0, 1)

    # --- Low-speed launch boost ---
    if S['speedX'] < 10:
        R['accel'] += 1 / (S['speedX'] + 0.1)

    # --- Traction control ---
    spin_diff = (S['wheelSpinVel'][2] + S['wheelSpinVel'][3]) - \
                (S['wheelSpinVel'][0] + S['wheelSpinVel'][1])
    if spin_diff > 5:
        R['accel'] -= 0.2

    # --- Automatic transmission (car1-ow1 has 7 gears) ---
    R['gear'] = 1
    if S['speedX'] >  30: R['gear'] = 2
    if S['speedX'] >  55: R['gear'] = 3
    if S['speedX'] >  80: R['gear'] = 4
    if S['speedX'] > 110: R['gear'] = 5
    if S['speedX'] > 150: R['gear'] = 6
    if S['speedX'] > 175: R['gear'] = 7

    # --- Unstick / wall-escape recovery ---
    # off_track fires only when the car is genuinely off the road surface.
    # TORCS trackPos ±1.0 = road boundary; >1.0 / <-1.0 = gravel/dirt.
    # Previous threshold 0.90 fired at the road edge on wide sweepers,
    # triggering reverse while the car was still on track (exp-19 failure mode).
    # Raising to 1.0 ensures recovery only activates when fully off-road.
    # The track[9] branch is gated on abs(trackPos) > 0.90 so it still only
    # fires when the car is well to the side AND has a wall dead ahead.
    off_track = (abs(S['trackPos']) > 1.0 or
                 (S['track'][9] < 2.0 and abs(S['trackPos']) > 0.90))
    if S['speedX'] < 15 and off_track:
        R['gear']  = -1
        R['accel'] = 0.5
        R['brake'] = 0.0
        # Steer toward track centre: negate trackPos, capped at ±0.7 (exp-28).
        # Hard lock (±1.0) made the car pivot in tight circles when deeply
        # off-track (trackPos ≈ ±1.6) instead of backing in a wide arc toward
        # the road.  Capping at 0.7 gives a gentler, more effective return arc.
        R['steer'] = clip(-S['trackPos'] * 0.5, -0.7, 0.7)

    # --- Post-recovery yaw realignment (exp-24) ---
    # Problem (exp-23): after reversing back to trackPos ≈ 0, the car resumed
    # normal drive with angle ≈ −1.26 rad (−72°).  Normal steering gave
    # steer = angle*5/PI ≈ −2.0 → clipped to −1.0, launching the car
    # sideways into the left barrier at 60 km/h.
    # Fix: if the car is back on the road (trackPos within ±1.0) but still
    # yawed more than 0.3 rad off the track heading AND there is enough
    # forward clearance (track[9] > 3 m), override to a gentle forward crawl
    # and steer toward zero angle until aligned.  (exp-28: added clearance
    # guard to prevent creeping into a wall 1 m ahead after recovery, which
    # froze the simulator in exp-27.)
    # 0.3 rad ≈ 17° — small enough to hand back control before a corner
    # but large enough to catch a sideways-facing car after recovery.
    elif abs(S['speedX']) < 15 and abs(S['angle']) > 0.3 and abs(S['trackPos']) < 1.0 and S['track'][9] > 3.0:
        # (exp-30) Speed guard: only apply yaw-recovery when nearly stopped.
        # At high speed, normal lookahead braking handles the corner; these
        # branches fired at 73 km/h in exp-29 (angle -0.31 rad, track[9] 2.86 m)
        # sending the car into reverse mid-corner and causing the wall-creep.
        # (exp-29) If the car is rolling backward, brake to a stop first.
        if S['speedX'] < -1.0:
            R['gear']  = 1
            R['accel'] = 0.0
            R['brake'] = 0.8
            R['steer'] = clip(S['angle'] * 3 / PI, -1, 1)
        else:
            R['gear']  = 1
            R['accel'] = 0.3
            R['brake'] = 0.0
            R['steer'] = clip(S['angle'] * 3 / PI, -1, 1)
    elif abs(S['speedX']) < 15 and abs(S['angle']) > 0.3 and abs(S['trackPos']) < 1.0 and S['track'][9] <= 3.0:
        # No forward clearance — keep reversing to create space before aligning.
        # (exp-30) Speed guard applied here too for the same reason.
        R['gear']  = -1
        R['accel'] = 0.4
        R['brake'] = 0.0
        R['steer'] = clip(S['angle'] * 3 / PI, -1, 1)


# ================ MAIN ================
if __name__ == "__main__":
    C   = Client(p=3001)
    rec = Recorder(exp_tag=EXP_TAG, track_id=C.trackname)
    _last_S = {}
    try:
        for step in range(C.maxSteps, 0, -1):
            C.get_servers_input()
            if not C.so:          # server sent ***shutdown*** — race over
                break
            drive_example(C)                  # controls computed here
            rec.record_step(C.S.d, C.R.d)    # record AFTER compute, BEFORE send
            C.respond_to_server()             # send controls to simulator
            _last_S = C.S.d
    except KeyboardInterrupt:
        print('\n[Recorder] Ctrl+C — writing partial summary')
    finally:
        rec.close_partial(_last_S, reason='max_steps_or_interrupt')
        C.shutdown()
