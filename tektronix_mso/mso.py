"""EPICS PVAccess server for Tektronix MSO oscilloscopes using epicsdev module."""
# pylint: disable=invalid-name
__version__ = 'v2.0.1 26-03-05'# Enabled autosave and putLog functionality. Low limit for recLengthS was changed to 1000.
# Note, visa INSTR works more reliably than SOCKET, but waveform acquisition is ~10 times slower
#TODO: Timing does not match for 0.3 s: cycleTime=2.0, acquire_wf=0.7, sleep=1.0
import sys
import time
from time import perf_counter as timer
import argparse
import threading
import numpy as np

import pyvisa as visa
from pyvisa.errors import VisaIOError

from epicsdev.epicsdev import  Server, init_epicsdev, sleep,\
    serverState, set_server, publish, pvv,\
    printi, printe, printw, printv, printvv, __version__ as epicsdev_version

#``````````````````Constants
Threadlock = threading.Lock()
OK = 0
NotOK = -1
IF_CHANGED =True
ElapsedTime = {}
NDIVSX = 10# number of horizontal divisions of the scope display
NDIVSY = 10# number of vertical divisions
BigEndian = False# Defined in configure_scope(WFMOUTPRE:BYT_Or LSB)
#``````````````````PVs defined here```````````````````````````````````````````
def myPVDefs():
    """PV definitions"""
    F, SET, U, LL, LH, SCPI = 'features', 'setter', 'units', 'limitLow', 'limitHigh', 'scpi'
    pvDefs = [
# instruments's PVs
['setup', 'Save/recall instrument state to/from latest or operational setup',
    ['Setup','Save latest','Save oper','Recall latest','Recall oper'],
    {F:'WD', SET:set_setup}],
['visaResource', 'VISA resource to access the device', pargs.resource, {F:'R'}],
['dateTime',    'Scope`s date & time', 'N/A', {}],
['acqCount',    'Number of acquisition recorded', 0, {}],
['scopeAcqCount',  'Acquisition count of the scope', 0,{
    SCPI:'ACQuire:NUMACq'}],
['lostTrigs',   'Number of triggers lost',  0, {}],
['instrCtrl',   'Scope control commands',
    '*IDN?,*RST,*CLS,*ESR?,*OPC?,*STB?'.split(','), {F:'WD'}],
['instrCmdS',   'Execute a scope command. Features: RWE',  '*IDN?',{F:'W',
    SET:set_instrCmdS}],
['instrCmdR',   'Response of the instrCmdS',  '', {}],
['actOnEvent',  'Enables the saving waveforms on trigger', ['0','1'],{F:'WD',
    SCPI:'ACTONEVent:ENable', SET:set_scpi}],
['aOE_Limit',   'Limit of Action On Event saves', 80,{F:'W',
    SCPI:'ACTONEVent:LIMITCount', SET:set_scpi}],
#``````````````````Horizontal PVs
['horzMode',    'Horizontal mode', ['AUTO','MANUAL'],{F:'WD',
    SCPI:'HORizontal:MODE', SET:set_scpi}],
['recLengthS',  'Number of points per waveform', 1000.,{F:'W',
    SCPI:'HORizontal:RECOrdlength', SET:set_scpi, LL:1000, LH:10000000}],
['recLengthR',  'Number of points per waveform read', 0.,{
    SCPI:'HORizontal:RECOrdlength'}],
['samplingRate', 'Sampling Rate',  0., {U:'Hz',
    SCPI:'HORizontal:SAMPLERate'}],
['timePerDiv', f'Horizontal scale (1/{NDIVSX} of full scale)', 2.e-6, {F:'W', U:'S/du',
    SCPI: 'HORizontal:SCAle', SET:set_scpi}],
['tAxis',       'Horizontal axis array', [0.], {U:'S'}],

#``````````````````Trigger PVs
['trigger',     'Click to force trigger event to occur',
    ['Trigger','Force!'], {F:'WD', SET:set_trigger}],
['trigType',   'Trigger type',
    ['EDGE','WIDTH','TIMEOUT','RUNT','WINDOW','LOGIC','SETHOLD','TRANSITION','BUS'],{F:'WD',
    SCPI:'TRIGger:A:TYPE',SET:set_scpi}],
['trigCoupling',   'Trigger coupling', ['DC','HFREJ','LFREJ','NOISEREJ'],{F:'D',
    SCPI:'TRIGger:A:EDGE:COUPling'}],
['trigState',   'Current trigger status', '?',{
    SCPI:'TRIGger:STATE'}],
['trigMode',   'Trigger mode', ['AUTO','NORMAL'],{F:'WD',
    SCPI:'TRIGger:A:MODe',SET:set_scpi}],
['trigDelay',   'Horizontal delay time', 0., {U:'S',
    SCPI:'HORizontal:DELay:TIMe'}],
['trigSource', 'Trigger source',
    pargs.channelList+['LINE','AUX'],{F:'WD',
    SCPI:'TRIGger:A:EDGE:SOUrce',SET:set_scpi}],
['trigSlope',  'Trigger slope', ['RISE','FALL','EITHER'],{F:'WD',
    SCPI:'TRIGger:A:EDGE:SLOpe',SET:set_scpi}],
['trigLevel', 'Trigger level', 0., {F:'W', U:'V',SET:set_trigLevel}],
#``````````````````Auxiliary PVs
['timing',  'Performance timing: trigger,waveforms,preamble,query,publish', [0.], {U:'S'}],
    ]

    #``````````````Templates for channel-related PVs.
    # The <n> in the name will be replaced with channel number.
    ChannelTemplates = [
['c<n>OnOff', 'Enable/disable channel', ['1','0'],{F:'WD',
    SCPI:'DISplay:WAVEView1:CH<n>:STATE', SET:set_scpi}],
['c<n>Coupling', 'Channel coupling', ['DC','AC','DCREJ'],{F:'WD',
    SCPI:'CH<n>:COUPling', SET:set_scpi}],
['c<n>VoltsPerDiv',  'Vertical scale',  1E-3, {F:'W', U:'V/du',
    SCPI:'CH<n>:SCAle', SET:set_scpi, LL:500E-6, LH:10.}],
['c<n>VoltOffset',  'Vertical offset',  0., {F:'W', U:'V',
    SCPI:'CH<n>:OFFSet', SET:set_scpi, LL:-10., LH:10.}],
['c<n>Termination', 'Input termination', '50.000', {F:'W', U:'Ohm',
    SCPI:'CH<n>:TERmination', SET:set_scpi}],
['c<n>Waveform', 'Waveform array',           [0.], {U:'du'}],
['c<n>Mean',     'Mean of the waveform',     0., {U:'du'}],
['c<n>Peak2Peak','Peak-to-peak amplitude',   0., {U:'du'}],
    ]
    # extend PvDefs with channel-related PVs
    for ch in range(pargs.channels):
        for pvdef in ChannelTemplates:
            newpvdef = pvdef.copy()
            newpvdef[0] = pvdef[0].replace('<n>',f'{ch+1:02}')
            pvDefs.append(newpvdef)
    return pvDefs
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
class C_():
    """Namespace for module properties"""
    scope = None
    scpi = {}# {pvName:SCPI} map
    setterMap = {}
    PvDefs = []
    readSettingQuery = None
    exceptionCount = {}
    numacq = 0
    triggersLost = 0
    trigTime = 0
    previousScopeParametersQuery = ''
    channelsTriggered = []
    npoints = 0
    #ypars = None
    ymult = []
    yoff = []# not used
    yzero = []
#``````````````````Setters````````````````````````````````````````````````````
def scopeCmd(cmd):
    """Send command to scope, return reply if any."""
    printv(f'>scopeCmd: {cmd}')
    reply = None
    try:
        if cmd[-1] == '?':
            with Threadlock:
                reply = C_.scope.query(cmd)
        else:
            with Threadlock:
                C_.scope.write(cmd)
    except:
        handle_exception(f'in scopeCmd{cmd}')
    return reply

def set_instrCmdS(cmd, *_):
    """Setter for the instrCmdS PV"""
    publish('instrCmdR','')
    reply = scopeCmd(cmd)
    if reply is not None:
        publish('instrCmdR',reply)
    publish('instrCmdS',cmd)

def serverStateChanged(newState:str):
    """Start device function called when server is started"""
    if newState == 'Start':
        printi('start_device called')
        configure_scope()
        adopt_local_setting()
        with Threadlock:
            C_.scope.write(':RUN')
    elif newState == 'Stop':
        printi('stop_device called')
    elif newState == 'Clear':
        printi('clear_device called')

def set_setup(action_slot, *_):
    """setter for the setup PV"""
    if action_slot == 'Setup':
        return OK
    action,slot = str(action_slot).split()
    filename = 'oper.set' if 'oper' in slot else 'latest.set'
    print(f'set_setup: {action}')
    if action == 'Save':
        status = 'Setup was saved'
        with Threadlock:
            C_.scope.write(f"SAVE:SETUP 'c:/{filename}'")
        printi(status)
    elif action == 'Recall':
        status = 'Setup was recalled'
        if serverState().startswith('Start'):
            printw('Please set server to Stop before Recalling')
            publish('setup','Setup')
            return NotOK
        with Threadlock:
            C_.scope.write(f"RECAll:SETUp 'c:/{filename}'")
        printi(status)
    else:
        status = f'Wrong setup action: {action}'
        printw(status)
    publish('setup','Setup')
    if action == 'Recall':
        adopt_local_setting()
    return OK

def set_trigger(value, *_):
    """setter for the trigger PV"""
    printv(f'set_trigger: {value}')
    if str(value) == 'Force!':
        with Threadlock:
            C_.scope.write('TRIGger FORCe')
        publish('trigger','Trigger')

def set_trigLevel(value, *_):
    """setter for the trigLevel PV"""
    printv(f'set_trigLevel: {value}')
    with Threadlock:
        C_.scope.write(trigLevelCmd() + f' {value}')
        value = C_.scope.query(trigLevelCmd() + '?')
    publish('trigLevel', value)

def set_recLengthS(value, *_):
    """setter for the recLengthS PV"""
    printv(f'set_recLengthS: {value}')
    with Threadlock:
        C_.scope.write(f'HORizontal:RECOrdlength {value}')
    publish('recLengthS', value)

def set_scpi(value, pv, *_):
    """setter for SCPI-associated PVs"""
    printv(f'set_scpi({value},{pv.name})')
    scpi = C_.scpi.get(pv.name,None)
    if scpi is None:
        printe(f'No SCPI defined for PV {pv.name}')
        return
    scpi = scpi.replace('<n>',pv.name[2])# replace <n> with channel number
    #TODO?scpi += f' {value}' if pv.writable else '?'
    scpi += f' {value}'
    if pv.name == 'recLengthS':
        scpi = f':HORizontal:MODE MANUAL;:{scpi}'
        print(f'setting recLengthS: {scpi}')
    printv(f'set_scpi command: {scpi}')
    reply = scopeCmd(scpi)
    if reply is not None:
        publish(pv.name, reply)
    publish(pv.name, value)

#``````````````````Instrument communication functions`````````````````````````
def query(pvnames, explicitSCPIs=None):
    """Execute query request of the instrument for multiple PVs"""
    scpis = [C_.scpi[pvname] for pvname in pvnames]
    if explicitSCPIs:
        scpis += explicitSCPIs
    combinedScpi = '?;:'.join(scpis) + '?'
    #print(f'combinedScpi: {combinedScpi}')
    with Threadlock:
        r = C_.scope.query(combinedScpi)
    return r.split(';')

def configure_scope():
    """Send commands to configure data transfer"""
    printi('configure_scope')
    with Threadlock:
        # Configure waveform data transfer for Tektronix
        C_.scope.write('HORizontal:DELay:MODe ON')
        C_.scope.write('HORizontal:MODE MANual')
        C_.scope.write('HORizontal:MODE:MANual:CONFIGure HORIZontalscale')
        C_.scope.write((  ':WFMOUTPRE:ENCdg BINARY;'
                        ':WFMOUTPRE:BN_Fmt RI;'
                        ':WFMOUTPRE:BYT_NR 2;'
                        f':WFMOUTPRE:BYT_Or LSB;'))

def update_scopeParameters():
    """Update sensitive scope parameters"""
    #printi(f'Updating scope parameters for {pargs.channels} channels')
    r = query(['horzMode'])
    publish('horzMode', r[0], IF_CHANGED)
    for ich in range(1,pargs.channels+1):
        C_.scope.write(f'DATA:SOURCE CH{ich}')
        with Threadlock:
            r = C_.scope.query('WFMOutpre:YMUlt?;:WFMOutpre:YOFf?;:WFMOutpre:YZEro?').split(';')
        C_.ymult[ich] = float(r[0])
        C_.yoff[ich] = float(r[1])
        C_.yzero[ich] = float(r[2])
        #print(f'Channel {ich}: YMULT={C_.ymult[ich]}, YOFF={C_.yoff[ich]}, YZERO={C_.yzero[ich]}')

    # Query horizontal parameters
    with Threadlock:
        r = C_.scope.query('WFMOutpre:XINcr?;:WFMOutpre:XZEro?;:WFMOutpre:NR_Pt?').split(';')
        xincr = float(r[0])
        xzero = float(r[1])
        npoints = int(r[2])
        
        # Query channel states
        ch_states = []
        for ch in range(1, pargs.channels+1):
            state = C_.scope.query(f"CH{ch}:STATE?")
            ch_states.append(state.strip())
    
    currentScopeParameters = f'{xincr:.6g};{npoints};' + ';'.join(ch_states)
    
    if currentScopeParameters != C_.previousScopeParametersQuery:
        printi(f'Scope parameters changed dx,n: {currentScopeParameters}')
        xorigin = xzero
        xincrement = xincr
        C_.npoints = npoints
        taxis = np.arange(0, C_.npoints) * xincrement + xorigin
        publish('tAxis', taxis)
        publish('recLengthR', C_.npoints, IF_CHANGED)
        publish('timePerDiv', C_.npoints*xincrement/NDIVSX, IF_CHANGED)
        publish('samplingRate', 1./xincrement, IF_CHANGED)
    C_.previousScopeParametersQuery = currentScopeParameters

def init_visa():
    '''Init VISA interface to device'''
    try:
        rm = visa.ResourceManager('@py')
    except ModuleNotFoundError as e:
        printe(f'in visa.ResourceManager: {e}')
        sys.exit(1)

    resourceName = pargs.resource.upper()
    printv(f'Opening resource {resourceName}')
    try:
        C_.scope = rm.open_resource(resourceName)#, open_timeout=5000)
    except visa.errors.VisaIOError as e:
        printe(f'Could not open resource {resourceName}: {e}')
        sys.exit(1)
    except Exception as e:
        printe(f'Exception: Could not open resource {resourceName}: {e}')
        sys.exit(1)
    #C_.scope.set_visa_attribute( visa.constants.VI_ATTR_TERMCHAR_EN, True)
    C_.scope.timeout = 5000 # ms
    #C_.scope.encoding = 'latin_1'
    C_.scope.read_termination = '\n'
    C_.scope.write_termination = '\n'
    
    try:
        C_.scope.clear()
        print("Instrument buffer cleared successfully.")
    except Exception as e:
        print(f"An error occurred during clearing the buffer: {e}")
        sys.exit(1)
    #time.sleep(.1)
    try:
        idn = C_.scope.query('*IDN?')
    except Exception as e:
        printe(f"An error occurred during IDN query: {e}")
        if 'SOCKET' in resourceName:
            print('You may need to disable VXI server on the instrument.')
        sys.exit(1)
    print(f'IDN: {idn}')
    if not 'TEKTRONIX' in idn.upper():
        print('ERROR: instrument is not TEKTRONIX')
        sys.exit(1)

    try:
        C_.scope.write('*CLS') # clear ESR, previous error messages will be cleared
        pass
    except Exception as e:
        printe(f'Resource {resourceName} not responding: {e}')
        sys.exit()

#``````````````````````````````````````````````````````````````````````````````
def handle_exception(where):
    """Handle exception"""
    #print('handle_exception',sys.exc_info())
    exceptionText = str(sys.exc_info()[1])
    tokens = exceptionText.split()
    msg = tokens[0] if tokens[0] == 'VI_ERROR_TMO' else exceptionText
    msg = msg+': '+where
    printw(msg)
    with Threadlock:
        C_.scope.write('*CLS')
    return -1

def adopt_local_setting():
    """Read scope setting and update PVs"""
    printi('adopt_local_setting')
    ct = time.time()
    nothingChanged = True
    try:
        with Threadlock:
            values = C_.scope.query(C_.readSettingQuery).split(';')
        printvv(f'parnames[{len(C_.scpi)}]: {C_.scpi.keys()}')
        printvv(f'values[{len(values)}]: {values}')
        if len(C_.scpi) != len(values):
            printv(f'values length mismatch: {len(values)} vs {len(C_.scpi)}')
            printvv(f'par:value: {[ (k,v) for k,v in zip(C_.scpi, values)]}')
            l = min(len(C_.scpi),len(values))
            printe(f'adopt_local_setting failed for {list(C_.scpi.keys())[l]}')
            sys.exit(1)
        for parname,v in zip(C_.scpi, values):
            publish(parname, v, IF_CHANGED)
        # special case of TrigLevel
        with Threadlock:
            value = C_.scope.query(trigLevelCmd()+'?')
        publish('trigLevel', value, IF_CHANGED)
    except:
        handle_exception('in adopt_local_setting')
        return
    if nothingChanged:
        printi('Local setting did not change.')

#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````Acquisition-related functions`````````````````````````````````
def trigger_is_detected():
    """check if scope was triggered"""
    printv('Checking if trigger is detected...')
    ts = timer()
    try:
        r = query(['trigState','scopeAcqCount','recLengthR',
                    'timePerDiv'], ['DATa:SOUrce:AVAILable'])
        #print(f'Result of query: {r}')
    except visa.errors.VisaIOError as e:
        printe(f'Exception in query for trigger: {e}')
        for exc in C_.exceptionCount:
            if exc in str(e):
                C_.exceptionCount[exc] += 1
                errCountLimit = 2
                if C_.exceptionCount[exc] >= errCountLimit:
                    printe(f'Processing stopped due to {exc} happened {errCountLimit} times')
                    set_server('Exit')
                else:
                    printw(f'Exception  #{C_.exceptionCount[exc]} during processing: {exc}')
        return False

    # last query was successfull, clear error counts
    for i in C_.exceptionCount:
        C_.exceptionCount[i] = 0
    try:
        trigstate,numacq,rl,timePerDiv,channelsTriggered = r
    except Exception as e:
        printw(f'wrong trig info: {r}, exception:{e}')
        return False

    numacq = int(numacq)
    C_.channelsTriggered = channelsTriggered.split(',')
    #print(f'Channels triggered: {C_.channelsTriggered}')
    if numacq == 0 or C_.numacq == 0:
        C_.triggersLost = 0
    else:
        C_.triggersLost += numacq - C_.numacq - 1
    C_.triggersLost = max(C_.triggersLost, 0)
    if numacq <= C_.numacq:
        if numacq == C_.numacq:
            publish('status',f'WAR: Scope not acquiring. numacq={numacq}, C_.numacq={C_.numacq}')
        else:
            printw(f'Scope acquisition count was reset. Something changed in the scope settings.')
        C_.numacq = numacq
        return False

    # trigger detected
    C_.numacq = numacq
    C_.trigTime = time.time()
    d = {'recLengthR': int(rl), 'timePerDiv': float(timePerDiv),
         'trigState':trigstate}
    for pvname,value in d.items():
        publish(pvname, value, IF_CHANGED, t=C_.trigTime)
    ElapsedTime['trigger_detection'] = round(timer()-ts,6)
    printv(f'Trigger detected {C_.numacq}')
    return True

def trigLevelCmd():
    """Generate SCPI command for trigger level control"""
    ch = str(pvv('trigSource'))
    if ch[:2] != 'CH':
        return ''
    r = 'TRIGger:A:LEVel:'+ch
    printv(f'tlcmd: {r}')
    return r

#``````````````````Acquisition-related functions``````````````````````````````
def acquire_waveforms():
    """Acquire waveforms from the device and publish them."""
    channels = C_.channelsTriggered
    printv(f'>acquire_waveform for channels {channels}')
    publish('acqCount', pvv('acqCount') + 1, t=C_.trigTime)
    ElapsedTime['acquire_wf'] = timer()
    ElapsedTime['preamble'] = 0.
    ElapsedTime['query_wf'] = 0.
    ElapsedTime['publish_wf'] = 0.
    if channels[0] == 'NONE':
        channels = []
    for chstr in channels:
        #print(f'Acquiring waveform for channel {chstr}')
        ch = int(chstr[2])
        # refresh scalings
        ts = timer()
        operation = 'getting preamble'
        try:
            with Threadlock:
                C_.scope.write(f'DATa:SOUrce CH{ch}')
                # Get waveform parameters
                # This section is 4 times longer than the waveform acquisition
                #TODO: do this in periodic_update
                # ymult = float(C_.scope.query('WFMOutpre:YMUlt?'))
                # yoff = float(C_.scope.query('WFMOutpre:YOFf?'))
                # yzero = float(C_.scope.query('WFMOutpre:YZEro?'))
            dt = timer() - ts
            ts = timer()
            #printvv(f'aw preamble{ch}: ymult={C_.ymult[ch]}, yoff={C_.yoff[ch]}, yzero={C_.yzero[ch]}, dt: {dt}')
            ElapsedTime['preamble'] += dt

            # acquire the waveform
            operation = 'getting waveform'
            # with Threadlock: This is 4 times longer than the query_binary_values
            #     C_.scope.write('CURVe?')
            #     # Read binary data
            #     waveform = C_.scope.read_raw()
            #     # Parse Tektronix binary format
            #     # Format: #<x><yyy><data>
            #     # where x is number of digits in yyy, yyy is number of bytes
            #     header_len = 2 + int(chr(waveform[1]))
            #     data_bytes = waveform[header_len:-1]  # Skip header and terminator
            #     waveform_data = np.frombuffer(data_bytes, dtype=np.int16)
            try:
                with Threadlock:
                    bin_wave = C_.scope.query_binary_values('curve?',
                        datatype='h', is_big_endian=BigEndian,
                        container=np.array)
            except Exception as e:
                printe(f'in query_binary_values: {e}')
                break
            ElapsedTime['query_wf'] += timer() - ts
            ts = timer()

            # Convert to vertical divisions
            #v = (waveform_data - yoff) * ymult + yzero
            v = bin_wave*C_.ymult[ch] + C_.yzero[ch]
            v = v/pvv(f'c{ch:02}VoltsPerDiv')

            # publish
            operation = 'publishing'
            publish(f'c{ch:02}Waveform', v, t=C_.trigTime)
            publish(f'c{ch:02}Peak2Peak', np.ptp(v), t=C_.trigTime)
            publish(f'c{ch:02}Mean', np.mean(v), t=C_.trigTime)
        except visa.errors.VisaIOError as e:
            printe(f'Visa exception in {operation} for {ch}:{e}')
            break
        except Exception as e:
            printe(f'Exception in processing channel {ch}: {e}')
        ElapsedTime['publish_wf'] += timer() - ts
    ElapsedTime['acquire_wf'] = timer() - ElapsedTime['acquire_wf']
    printvv(f'elapsedTime: {ElapsedTime}')

def make_readSettingQuery():
    """Create combined SCPI query to read all settings at once"""
    for pvdef in C_.PvDefs:
        pvname = pvdef[0]
        # if setter is defined, add it to the setterMap
        setter = pvdef[3].get('setter',None)
        if setter is not None:
            C_.setterMap[pvname] = setter
        # if SCPI is defined, add it to the readSettingQuery
        scpi = pvdef[3].get('scpi',None)
        if scpi is None:
            continue
        scpi = scpi.replace('<n>',pvname[2])#
        scpi = ''.join([char for char in scpi if not char.islower()])# remove lowercase letters
        # check if scpi is correct:
        s = scpi+'?'
        try:
            with Threadlock:
                r = C_.scope.query(s)
        except VisaIOError as e:
            printe(f'Invalid SCPI in PV {pvname}: {scpi}? : {e}')
            sys.exit(1)
        printvv(f'SCPI for PV {pvname}: {scpi}, reply: {r}')
        if not scpi[0] in '!*':# only SCPI starting with !,* are not added
            C_.scpi[pvname] = scpi
       
    C_.readSettingQuery = '?;:'.join(C_.scpi.values()) + '?'
    printv(f'readSettingQuery: {C_.readSettingQuery}')
    #printv(f'setterMap: {C_.setterMap}')

def init():
    """Module initialization"""
    C_.ymult = [0.]*(pargs.channels+1)
    C_.yzero = [0.]*(pargs.channels+1)
    C_.yoff = [0.]*(pargs.channels+1)
    init_visa()
    make_readSettingQuery()
    #adopt_local_setting()
    update_scopeParameters()
    #publish('version', __version__)

def periodicUpdate():
    """Called for infrequent updates"""
    printvv(f'periodicUpdate')
    try:
        update_scopeParameters()
    except:
        handle_exception('in update_scopeParameters')
    with Threadlock:
        r = C_.scope.query(':ACTONEVent:ENable?;:DATE?;:TIMe?').split(';')
        # the dateTime is here, because it is dual command
    dt = ' '.join(r[1:3]).replace('"','')
    #print(f'dateTime: {dt}, {r}')
    publish('dateTime', dt)
    publish('scopeAcqCount', C_.numacq, IF_CHANGED)
    publish('lostTrigs', C_.triggersLost, IF_CHANGED)
    publish('actOnEvent', r[0], IF_CHANGED)
    if 'STOP' in str(pvv('trigState')).upper():
        printe('Acquisition is stopped')
    publish('timing', [(round(i,6)) for i in ElapsedTime.values()])

def poll():
    """Example of polling function"""
    if trigger_is_detected():
        acquire_waveforms()

#``````````````````Main```````````````````````````````````````````````````````
if __name__ == "__main__":
    # Argument parsing
    parser = argparse.ArgumentParser(description = __doc__,
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    epilog=f'{__version__}, epicsdev {epicsdev_version}')
    parser.add_argument('-a', '--autosave', nargs='?', default='', help=
    'Autosave control. If not given, then autosave is enabled with default file '\
    'name /tmp/<device><index>.cache. ' \
    'If given without argument, then autosave is disabled' \
    'If a file name is given, then it is used for autosave.')
    parser.add_argument('-c', '--recall', action='store_false', help=
    'If given: Do not load initial values from pvCache file. That is useful when you want to start with default values, but do not want to disable autosave. By default, the initial values are loaded from the cache file if it exists.')
    parser.add_argument('-C', '--channels', type=int, default=6, help=
    'Number of channels per device')
    parser.add_argument('-d', '--device', default='tektronix', help=
    'Device name, the PV name will be <device><index>:')
    parser.add_argument('-i', '--index', default='0', help=
    'Device index, the PV name will be <device><index>:') 
    parser.add_argument('-r', '--resource', default='TCPIP::192.168.1.100::5025::SOCKET', help=
    'Resource string to access the device, e.g., TCPIP::192.168.1.100::INSTR. Note, the INSTR is more reliable, SOCKET is faster for long waveforms')
    parser.add_argument('-p', '--putlogPV', default='putlog:dump', help=
'Name of the PV where put operations are logged. If None, then put operations are not logged.')
    parser.add_argument('-v', '--verbose', action='count', default=0, help=
    'Show more log messages (-vv: show even more)') 
    pargs = parser.parse_args()
    print(f'pargs: {pargs}')
    pargs.channelList = [f'CH{i+1}' for i in range(pargs.channels)]

    # Initialize epicsdev and PVs
    pargs.prefix = f'{pargs.device}{pargs.index}:'
    C_.PvDefs = myPVDefs()
    PVs = init_epicsdev(pargs.prefix, C_.PvDefs, pargs.verbose,
        serverStateChanged, autosaveDir=pargs.autosave, recall=pargs.recall,
        putlogPV=pargs.putlogPV)

    # Initialize the device
    init()

    # Start the Server
    set_server('Start')

    # Main loop with Server
    server = Server(providers=[PVs])
    printi(f'Server for {pargs.prefix} started...')
    while True:
        state = serverState()
        if state.startswith('Exit'):
            break
        if not state.startswith('Stop'):
            poll()
        if not sleep():
            periodicUpdate()
    printi('Server is exited')
