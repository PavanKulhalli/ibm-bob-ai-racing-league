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
PI= 3.14159265359

# ---- Experiment tag -------------------------------------------------------
# Change this each time you start a new experiment so lap_summary.csv rows
# can be filtered by experiment without touching the raw lap_data.csv.
EXP_TAG = "exp-18-baseline"
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
        if self.d['gear'] not in [-1, 0, 1, 2, 3, 4, 5, 6]:
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

class Recorder:
    '''Writes two CSV files that accumulate across all runs of this script.

    lap_data.csv   — one row per server tick (~50 Hz); never truncated.
    lap_summary.csv — one row per completed or interrupted lap; never truncated.

    Both files are opened in append mode so each new run adds rows to the
    existing data.  A fresh run_id (timestamp + short UUID) is minted at
    startup to make individual runs distinguishable in the data.
    '''

    LAP_DATA_PATH    = 'lap_data.csv'
    LAP_SUMMARY_PATH = 'lap_summary.csv'

    LAP_DATA_HEADER = [
        'run_id', 'exp_tag', 'tick',
        'lap', 'curLapTime', 'distFromStart', 'distRaced',
        'speedX', 'speedY', 'angle', 'trackPos',
        'ahead', 'safe_kmh', 'target_speed',
        'accel', 'brake', 'steer', 'gear',
        'damage', 'track9',
        'wheelSpin_fl', 'wheelSpin_fr', 'wheelSpin_rl', 'wheelSpin_rr',
        'rpm', 'fuel',
    ]

    LAP_SUMMARY_HEADER = [
        'run_id', 'exp_tag',
        'lap', 'completed',
        'lap_time', 'dist_raced',
        'damage_start', 'damage_end', 'damage_delta',
        'top_speed', 'avg_speed',
        'crash_time',
    ]

    def __init__(self, exp_tag):
        self.exp_tag  = exp_tag
        self.run_id   = (datetime.datetime.now().strftime('%Y%m%d_%H%M%S') +
                         '_' + uuid.uuid4().hex[:6])
        self.tick     = 0

        # Per-lap accumulators
        self._lap_prev      = 0
        self._damage_start  = 0.0
        self._lap_speeds     = []
        self._lap_top_speed  = 0.0
        self._lap_dist_start = 0.0
        self._lap_start_time = 0.0   # curLapTime at last lap-start (always 0)

        self._data_file    = open(self.LAP_DATA_PATH,    'a', newline='')
        self._summary_file = open(self.LAP_SUMMARY_PATH, 'a', newline='')
        self._data_writer    = csv.writer(self._data_file)
        self._summary_writer = csv.writer(self._summary_file)

        # Write headers only if the files are new (empty)
        if self._data_file.tell() == 0:
            self._data_writer.writerow(self.LAP_DATA_HEADER)
        if self._summary_file.tell() == 0:
            self._summary_writer.writerow(self.LAP_SUMMARY_HEADER)

        print('[Recorder] run_id=%s  exp_tag=%s' % (self.run_id, self.exp_tag))
        print('[Recorder] appending to %s and %s' %
              (self.LAP_DATA_PATH, self.LAP_SUMMARY_PATH))

    # ------------------------------------------------------------------
    def record_tick(self, S, R, ahead, safe_kmh, target_speed):
        '''Call once per tick after drive_example() has set R values.'''
        self.tick += 1
        lap      = int(S.get('lap', 1))
        cur_time = S.get('curLapTime', 0.0)
        speed    = S.get('speedX', 0.0)
        damage   = S.get('damage', 0.0)
        ws       = S.get('wheelSpinVel', [0, 0, 0, 0])
        dist     = S.get('distFromStart', 0.0)
        dist_r   = S.get('distRaced', 0.0)

        # --- Detect lap transition ---
        if lap != self._lap_prev:
            # A lap just completed (or race just started for lap 0→1)
            if self._lap_prev > 0:
                self._flush_lap_summary(
                    lap_number  = self._lap_prev,
                    completed   = True,
                    lap_time    = S.get('lastLapTime', 0.0),
                    dist_raced  = dist_r,
                    damage_end  = damage,
                    crash_time  = '',
                )
            # Reset accumulators for new lap
            self._damage_start  = damage
            self._lap_speeds    = []
            self._lap_top_speed = 0.0
            self._lap_dist_start = dist
            self._lap_prev      = lap

        # Accumulate speed stats for current lap
        self._lap_speeds.append(speed)
        if speed > self._lap_top_speed:
            self._lap_top_speed = speed

        # --- Write tick row ---
        self._data_writer.writerow([
            self.run_id, self.exp_tag, self.tick,
            lap, round(cur_time, 3), round(dist, 1), round(dist_r, 1),
            round(speed, 2),
            round(S.get('speedY', 0.0), 2),
            round(S.get('angle', 0.0), 4),
            round(S.get('trackPos', 0.0), 4),
            round(ahead, 2),
            round(safe_kmh, 2),
            round(target_speed, 2),
            round(R.get('accel', 0.0), 3),
            round(R.get('brake', 0.0), 3),
            round(R.get('steer', 0.0), 4),
            int(R.get('gear', 1)),
            round(damage, 0),
            round(S.get('track', [0]*19)[9], 2),
            round(ws[0], 2), round(ws[1], 2),
            round(ws[2], 2), round(ws[3], 2),
            round(S.get('rpm', 0.0), 0),
            round(S.get('fuel', 0.0), 2),
        ])

    # ------------------------------------------------------------------
    def record_dnf(self, S):
        '''Call when the race ends without a clean lap finish.'''
        if self._lap_prev < 1:
            return   # nothing to summarise — never got past the start line
        damage_now = S.get('damage', 0.0)
        cur_time   = S.get('curLapTime', 0.0)
        self._flush_lap_summary(
            lap_number  = self._lap_prev,
            completed   = False,
            lap_time    = cur_time,
            dist_raced  = S.get('distRaced', 0.0),
            damage_end  = damage_now,
            crash_time  = '%.3f' % cur_time,
        )

    # ------------------------------------------------------------------
    def _flush_lap_summary(self, lap_number, completed,
                           lap_time, dist_raced, damage_end, crash_time):
        avg = (sum(self._lap_speeds) / len(self._lap_speeds)
               if self._lap_speeds else 0.0)
        self._summary_writer.writerow([
            self.run_id, self.exp_tag,
            lap_number, completed,
            round(lap_time, 3),
            round(dist_raced, 1),
            round(self._damage_start, 0),
            round(damage_end, 0),
            round(damage_end - self._damage_start, 0),
            round(self._lap_top_speed, 1),
            round(avg, 2),
            crash_time,
        ])
        self._data_file.flush()
        self._summary_file.flush()

    # ------------------------------------------------------------------
    def close(self):
        self._data_file.close()
        self._summary_file.close()


# ===========================================================================
# Driver — working copy (exp-18 baseline; tune below and update EXP_TAG)
# ===========================================================================

def drive_example(c):
    '''Working-copy driver — exp-18 baseline.  See CHANGELOG.md for history.

    Baseline parameters (snakeoil3_v1.py / exp-18):
      ahead        : max of ±4° forward sensors (indices 6-14)
      steer gain   : angle * 5 / PI
      centre pull  : trackPos * 0.25  (linear only)
      decel_g      : 16.0 m/s²
      margin       : 0.88  (target = 88% of physics-safe speed)
      floor        : 10 km/h
      throttle band: 10%
      brake divisor: 35
      off-track gate: trackPos > 0.90 OR (track[9] < 2m AND trackPos > 0.85)

    To run an experiment:
      1. Change ONE value below.
      2. Update EXP_TAG at the top of the file (e.g. "exp-19").
      3. Run — data writes to lap_data.csv / lap_summary.csv.
      4. Record in CHANGELOG.md.  If clean → promote to snakeoil3_v1.py.
    Returns a dict of computed telemetry values for the recorder.
    '''
    S, R = c.S.d, c.R.d

    # --- Forward clearance (±4° sensor cone, indices 6-14) ---
    ahead = max(max(S['track'][6:15]), 0.0)

    # --- Steering ---
    R['steer'] = S['angle'] * 5 / PI
    R['steer'] -= S['trackPos'] * 0.25

    # --- Lookahead braking + proportional throttle ---
    decel_g      = 16.0
    safe_ms      = (2.0 * decel_g * ahead) ** 0.5
    safe_kmh     = safe_ms * 3.6
    target_speed = clip(safe_kmh * 0.88, 10, 250)
    speed_error  = target_speed - S['speedX']

    if S['speedX'] <= target_speed:
        throttle_band = target_speed * 0.10
        R['accel'] = 1.0 if speed_error > throttle_band else clip(speed_error / throttle_band, 0, 1)
        R['brake'] = 0
    elif S['speedX'] <= safe_kmh:
        R['accel'] = 0
        R['brake'] = 0
    else:
        R['accel'] = 0
        R['brake'] = clip((S['speedX'] - safe_kmh) / 35.0, 0, 1)

    # --- Low-speed launch boost ---
    if S['speedX'] < 10:
        R['accel'] += 1 / (S['speedX'] + 0.1)

    # --- Traction control ---
    if (S['wheelSpinVel'][2] + S['wheelSpinVel'][3]) - \
       (S['wheelSpinVel'][0] + S['wheelSpinVel'][1]) > 5:
        R['accel'] -= 0.2

    # --- Automatic transmission ---
    R['gear'] = 1
    if S['speedX'] >  30: R['gear'] = 2
    if S['speedX'] >  55: R['gear'] = 3
    if S['speedX'] >  80: R['gear'] = 4
    if S['speedX'] > 110: R['gear'] = 5
    if S['speedX'] > 130: R['gear'] = 6

    # --- Unstick / wall-escape recovery ---
    off_track = (abs(S['trackPos']) > 0.90 or
                 (S['track'][9] < 2.0 and abs(S['trackPos']) > 0.85))
    if S['speedX'] < 8 and off_track:
        R['gear']  = -1
        R['accel'] = 0.5
        R['brake'] = 0.0
        R['steer'] = clip(S['trackPos'], -1, 1)

    return ahead, safe_kmh, target_speed


# ================ MAIN ================
if __name__ == "__main__":
    C   = Client(p=3001)
    rec = Recorder(exp_tag=EXP_TAG)
    try:
        for step in range(C.maxSteps, 0, -1):
            C.get_servers_input()
            ahead, safe_kmh, target_speed = drive_example(C)
            C.respond_to_server()
            rec.record_tick(C.S.d, C.R.d, ahead, safe_kmh, target_speed)
    except KeyboardInterrupt:
        print('\n[Recorder] interrupted by user')
    finally:
        rec.record_dnf(C.S.d)
        rec.close()
        C.shutdown()
