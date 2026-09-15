"""EPICS PVAccess server for Tektronix MSO oscilloscopes using epicsdev module."""
# pylint: disable=invalid-name
__version__ = 'v3.0.2 2026-09-15'# Tested with TCPIP on MSO64 and USB on DPO2004B
# Note, visa INSTR works more reliably than SOCKET, but waveform acquisition is ~10 times slower
#TODO: Stop aqcquire during adopt_local_setting
#TODO: Timing does not match for 0.3 s: cycleTime=2.0, acquire_wf=0.7, sleep=1.0
import sys
import time
from time import perf_counter as timer
import argparse
from dataclasses import dataclass
#import threading
import re
import numpy as np

import pyvisa as visa
from pyvisa.errors import VisaIOError

from epicsdev.epicsdev import  Server, init_epicsdev, sleep,\
    serverState, set_server, publish, pvv,\
    printi, printe, printw, printv, printvv, __version__ as epicsdev_version

#``````````````````Constants
OK = 0
NotOK = -1
IF_CHANGED =True
ElapsedTime = {}
NDIVSX = 10# number of horizontal divisions of the scope display
NDIVSY = 10# number of vertical divisions
BigEndian = False# Defined in configure_scope(WFMOUTPRE:BYT_Or LSB)
MAX_CHANNELS = 8# maximum number of channels supported by the server
#Lock = threading.Lock()# to block sending commands during waveform receiving. Note: this deterministic code and locking is not necessary, but it is safer to avoid sending commands while receiving waveforms. It may be removed in the future.
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
['scopeIDN', 'Response to *IDN? query', 'N/A', {}],
['dateTime',    'Scope`s date & time', 'N/A', {}],
['acquire', 'Start/Stop acquisition', ['Start','Stop','Started','Stopped'],
    {F:'WD', SET:set_acquire}],
['acqCount',    'Number of acquisition recorded', 0, {}],
['scopeAcqCount',  'Acquisition count of the scope', 0,{
    SCPI:'ACQuire:NUMACq'}],
['lostTrigs',   'Number of triggers lost',  0, {}],
['instrCtrl',   'Scope control commands',
    '*IDN?,*RST,*CLS,*ESR?,*OPC?,*STB?'.split(','), {F:'WD'}],
['instrCmdS',   'Execute a scope command. Features: RWE',  '*IDN?',{F:'W',
    SET:set_instrCmdS}],
['instrCmdR',   'Response of the instrCmdS',  '', {}],
#``````````````````Horizontal PVs
['recLengthS',  'Number of points per waveform', 1000.,{F:'W', U:'pts',
    SCPI:'HORizontal:RECOrdlength', SET:set_scpi, LL:1000, LH:10000000}],
['recLengthR',  'Number of points per waveform read', 0., {U:'pts'}],
['samplingRate', 'Sampling Rate',  0., {U:'Hz',
    SCPI:'HORizontal:SAMPLERate'}],
['timePerDiv', f'Horizontal scale (1/{NDIVSX} of full scale)', 2.e-6, {F:'W', U:'S/div',
    SCPI: 'HORizontal:SCAle', SET:set_scpi}],
['tAxis',       'Horizontal axis array', [0.], {U:'S'}],

#``````````````````Trigger PVs
['trigger',     'Click to force trigger event to occur',
    ['Trigger','Force!'], {F:'WD', SET:set_trigger}],
['trigCoupling',   'Trigger coupling', ['DC','HFREJ','LFREJ','NOISEREJ'],{F:'D',
    SCPI:'TRIGger:A:EDGE:COUPling'}],
['trigState',   'Current trigger status', '?',{
    SCPI:'TRIGger:STATE'}],
['trigDelay',   'Horizontal delay time', 0., {U:'S',
    SCPI:'HORizontal:DELay:TIMe'}],
['trigSource', 'Trigger source',
    pargs.channelList+['LINE','AUX'],{F:'WD',
    SCPI:'TRIGger:A:EDGE:SOUrce',SET:set_scpi}],
['trigLevel', 'Trigger level', 0., {F:'W', U:'V',SET:set_trigLevel}],
#``````````````````Auxiliary PVs
['timing',  'Performance timing: trigger,waveforms,preamble,query,publish', [0.], {U:'S'}],
    ]

    #``````````````Templates for channel-related PVs.
    # The <n> in the name will be replaced with channel number.
    ChannelTemplates = [
['c<n>OnOff', 'Enable/disable channel', ['0','1'],{F:'WD',
    SCPI:'SELect:CH<n>', SET:set_scpi}],
['c<n>Coupling', 'Channel coupling', ['DC','AC','DCREJ'],{F:'WD',
    SCPI:'CH<n>:COUPling', SET:set_scpi}],
['c<n>VoltsPerDiv',  'Vertical scale',  1E-3, {F:'W', U:'V/div',
    SCPI:'CH<n>:SCAle', SET:set_scpi, LL:500E-6, LH:10.}],
['c<n>Offset',  'Vertical offset in display divisions',  0., {F:'W', U:'div',
    #SCPI:'CH<n>:OFFSet', SET:set_scpi, LL:-10., LH:10.}],
    LL:-10., LH:10.}],
['c<n>Termination', 'Input termination', '50.000', {F:'W', U:'Ohm',
    SCPI:'CH<n>:TERmination', SET:set_scpi}],
['c<n>Waveform', 'Waveform array in display divisions', [0.], {U:'div'}],
['c<n>Mean',     'Mean of the waveform',     0., {U:'V'}],
['c<n>Min', 'Waveform minimum', 0., {U:'V'}],
['c<n>Peak2Peak','Peak-to-peak amplitude',   0., {U:'V'}],
['c<n>RMS', 'RMS of waveform', 0.0, {U: 'V'}],
    ]
    # extend PvDefs with channel-related PVs
    for ch in range(pargs.channels):
        for pvdef in ChannelTemplates:
            newpvdef = pvdef.copy()
            newpvdef[0] = pvdef[0].replace('<n>',f'{ch+1:02}')
            pvDefs.append(newpvdef)

    if C_.scopeSeries == 'MSO':
        pvDefs.append(['actOnEvent', 'Enables the saving waveforms on trigger',
               ['0','1'],{F:'WD', SCPI:'ACTONEVent:ENable', SET:set_scpi}])
        pvDefs.append(['aOE_Limit',  'Limit of Action On Event saves', 80,{F:'W',
                SCPI:'ACTONEVent:LIMITCount', SET:set_scpi}])
        #TODO: DPO does not support HORizontal:MODE 
        pvDefs.append(['horzMode',    'Horizontal mode', ['AUTO','MANUAL'],{F:'WD',
            SCPI:'HORizontal:MODE', SET:set_scpi}])
        pvDefs.append(['trigType',   'Trigger type',
            ['EDGE','WIDTH','TIMEOUT','RUNT','WINDOW','LOGIC','SETHOLD','TRANSITION','BUS'],{F:'WD',
            SCPI:'TRIGger:A:TYPE',SET:set_scpi}])
        pvDefs.append(['trigMode',   'Trigger mode', ['AUTO','NORMAL'],{F:'WD',
            SCPI:'TRIGger:A:MODe',SET:set_scpi}])
        pvDefs.append(['trigSlope',  'Trigger slope', ['RISE','FALL','EITHER'],{F:'WD',
            SCPI:'TRIGger:A:EDGE:SLOpe',SET:set_scpi}])

    elif C_.scopeSeries == 'DPO':
        pvDefs.append(['trigType',   'Trigger type',
            ['EDG','WIDTH','TIMEOUT','RUNT','WINDOW','LOGIC','SETHOLD','TRANSITION'],{F:'WD',
            SCPI:'TRIGger:A:TYPE',SET:set_scpi}])
        pvDefs.append(['trigMode',   'Trigger mode', ['AUTO','NORM'],{F:'WD',
            SCPI:'TRIGger:A:MODe',SET:set_scpi}])
        pvDefs.append(['trigSlope',  'Trigger slope', ['RIS','FALL','EITHER'],{F:'WD',
            SCPI:'TRIGger:A:EDGE:SLOpe',SET:set_scpi}])
    return pvDefs    
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
@dataclass(slots=True)
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
    channelsEnabled = []
    npoints = 0
    #ypars = None
    scopeSeries = ''
    prevXpreamble =  (0., 0., 0)# xincr, xzero, recLength
    prevYpreamble = [(0., 0., 0., 1.)]*MAX_CHANNELS # yincr, yoffset, yzero, voltsPerDiv
#``````````````````Setters````````````````````````````````````````````````````
def scopeCmd(cmd):
    """Send blocking command to scope, return reply if any."""
    printv(f'>scopeCmd: {cmd}')
    reply = None
    try:
        if True:# with Lock:
            if cmd[-1] == '?':
                reply = C_.scope.query(cmd)
            else:
                C_.scope.write(cmd)
    except KeyboardInterrupt:
        raise
    except Exception:
        handle_exception(f'in scopeCmd: {cmd}')
    return reply

def set_instrCmdS(cmd, *_):
    """Setter for the instrCmdS PV"""
    publish('instrCmdR','')
    reply = scopeCmd(cmd)
    printv(f'set_instrCmdS: reply={reply}')
    if reply is not None:
        publish('instrCmdR',reply)
    publish('instrCmdS',cmd)

def serverStateChanged(newState:str):
    """Start device function called when server is started"""
    if newState == 'Start':
        printi('start_device called')
        configure_scope()
        adopt_local_setting()
        scopeCmd(':RUN')
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
    _acquire('Stop')
    if action == 'Save':
        status = 'Setup was saved'
        scopeCmd(f"SAVE:SETUP 'c:/{filename}'")
        printi(status)
    elif action == 'Recall':
        status = 'Setup was recalled'
        if serverState().startswith('Start'):
            printw('Please set server to Stop before Recalling')
            publish('setup','Setup')
            return NotOK
        scopeCmd(f"RECAll:SETUp 'c:/{filename}'")
        printi(status)
    else:
        status = f'Wrong setup action: {action}'
        printw(status)
    publish('setup','Setup')
    if action == 'Recall':
        adopt_local_setting()
    _acquire('Start')
    return OK

def set_trigger(value, *_):
    """setter for the trigger PV"""
    printv(f'set_trigger: {value}')
    if str(value) == 'Force!':
        scopeCmd('TRIGger FORCe')
        publish('trigger','Trigger')

def set_trigLevel(value, *_):
    """setter for the trigLevel PV"""
    printv(f'set_trigLevel: {value}')
    if (cmd := trigLevelCmd()):
        scopeCmd(cmd + f' {value}')
        value = C_.scope.query(cmd + '?')
        publish('trigLevel', value)

def set_recLengthS(value, *_):
    """setter for the recLengthS PV"""
    printv(f'set_recLengthS: {value}')
    scopeCmd(f'HORizontal:RECOrdlength {value}')
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
        printv(f'setting recLengthS: {scpi}')
    printv(f'set_scpi command: {scpi}')
    reply = scopeCmd(scpi)
    if reply is not None:
        publish(pv.name, reply)
    publish(pv.name, value)

def set_acquire(value, *_):
    """setter for the acquire PV"""
    if str(value) == 'Start':
        _acquire('Start')
        publish('acquire','Started')
    elif str(value) == 'Stop':
        _acquire('Stop')
        publish('acquire','Stopped')

#``````````````````Instrument communication functions`````````````````````````
def query(pvnames, explicitSCPIs=None):
    """Execute query request of the instrument for multiple PVs"""
    scpis = [C_.scpi[pvname] for pvname in pvnames]
    if explicitSCPIs:
        scpis += explicitSCPIs
    combinedScpi = '?;:'.join(scpis) + '?'
    #print(f'combinedScpi: {combinedScpi}')
    if True:# with Lock:
        r = C_.scope.query(combinedScpi)
    #print(f'query result: {r}')
    return r.split(';')

def configure_scope():
    """Send commands to configure data transfer"""
    printi('configure_scope')
    # Configure waveform data transfer for Tektronix
    scopeCmd('HORizontal:DELay:MODe ON')
    scopeCmd('HORizontal:MODE MANual')
    scopeCmd('HORizontal:MODE:MANual:CONFIGure HORIZontalscale')
    scopeCmd((  ':WFMOUTPRE:ENCdg BINARY;'
                    ':WFMOUTPRE:BN_Fmt RI;'
                    ':WFMOUTPRE:BYT_NR 2;'
                    ':WFMOUTPRE:BYT_Or LSB;'))

def refresh_channelsEnabled():
    """Refresh list of channels to read."""
    C_.channelsEnabled = []
    printv(f'Checking channels for {pargs.channels} available channels')
    for ch in range(pargs.channels):
        onoff = query([f'c{ch+1:02d}OnOff'])[0]
        #print(f'Channel {ch+1} OnOff: {onoff}')
        if onoff in ('1', 'ON', 'TRUE'):
            C_.channelsEnabled.append(f'CH{ch+1}')
        publish(f'c{ch+1:02d}OnOff', onoff, IF_CHANGED)
    printv(f'Channels enabled: {C_.channelsEnabled}')

def update_scopeParameters():
    """Update sensitive scope parameters"""
    #printi(f'Updating scope parameters for {pargs.channels} channels')
    #r = query(['horzMode'])
    #publish('horzMode', r[0], IF_CHANGED)
    refresh_channelsEnabled()  # Refresh the list of enabled channels

    # Query vertical parameters for each enabled channel
    for ch in C_.channelsEnabled:
        printv(f'Updating scope parameters for {ch}')
        scopeCmd(f'DATA:SOURCE {ch}')
        ich = int(ch[2])-1
        r = scopeCmd(
            f'WFMOutpre:YMUlt?;:WFMOutpre:YOFf?;:WFMOutpre:YZEro?;:{ch}:SCAle?').split(';')
        if len(r) != 4:
            printe(f'Unexpected number of vertical parameters for {ch}: {r}')
            continue
        #print(f'Vertical parameters query result for {ch}: {r}')
        ypreamble = tuple([float(i) for i in r])
        if ypreamble != C_.prevYpreamble[ich]:
            printi(f'Scope vertical parameters changed for {ch}: {ypreamble}')
            C_.prevYpreamble[ich] = ypreamble
            publish(f'c{ich+1:02d}VoltsPerDiv', ypreamble[3], IF_CHANGED)
            #publish(f'c{ich+1:02d}Offset', ypreamble[2], IF_CHANGED)

    # Query horizontal parameters
    r = scopeCmd('WFMOutpre:XINcr?;:WFMOutpre:XZEro?;:WFMOutpre:NR_Pt?;:ACQ:STATE?').split(';')
    #print(f'Horizontal parameters query result: {r}')
    xincr = float(r[0])
    xzero = float(r[1])
    C_.npoints = int(r[2])
    acq_state_str = 'Started' if r[3] == '1' else 'Stopped'
    acq_prev = str(pvv('acquire'))
    if acq_state_str != acq_prev:# IF_CHANGED does not work for enums in epicsdev 330
        #print(f'Acquisition state changed: {acq_state_str, acq_prev}')
        publish('acquire', acq_state_str, IF_CHANGED)
    xpreamble = (xincr, xzero, C_.npoints)
    if xpreamble != C_.prevXpreamble:
        printi(f'Horizontal scope parameters changed: {xpreamble}')
        taxis = np.arange(0, C_.npoints) * xincr + xzero
        #print(f'taxis: {taxis[0],taxis[-1]}')
        C_.prevXpreamble = xpreamble
        publish('tAxis', taxis)
        publish('recLengthR', C_.npoints, IF_CHANGED)
        publish('timePerDiv', C_.npoints*xincr/NDIVSX, IF_CHANGED)
        publish('samplingRate', 1./xincr, IF_CHANGED)

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
        print(f'ERROR: Exception: Could not open resource {resourceName}: {e}')
        availableResources = rm.list_resources()
        print(f'Available resources: {availableResources}')
        sys.exit(1)
    #C_.scope.set_visa_attribute( visa.constants.VI_ATTR_TERMCHAR_EN, True)
    C_.scope.timeout = 5000 # ms
    #C_.scope.encoding = 'latin_1'
    C_.scope.read_termination = '\n'
    C_.scope.write_termination = '\n'
    
    try:
        C_.scope.write('*CLS') # clear ESR, previous error messages will be cleared
    except Exception as e:
        print(f'ERROR:Resource {resourceName} not responding: {e}')
        sys.exit()
    try:
        C_.idn = C_.scope.query('*IDN?')
    except Exception as e:
        print(f"ERROR: occurred during IDN query: {e}")
        if 'SOCKET' in resourceName:
            print('You may need to disable VXI server on the instrument.')
        else:
            print('You may need to power cycle the instrument')
        sys.exit(1)
    print(f'IDN: {C_.idn}')
    if not 'TEKTRONIX' in C_.idn.upper():
        print('ERROR: instrument is not TEKTRONIX')
        sys.exit(1)

    modelName = C_.idn.split(',')[1]
    C_.scopeSeries = modelName[:3]
    modelNumber = re.findall(r'\d+', modelName)[0]
    print(f'Model name: {modelName}, series: {C_.scopeSeries}, model number: {modelNumber}')
    if pargs.channels is None:
        pargs.channels = int(modelNumber[-1])
        if pargs.channels > 16:
            print(f'ERROR: Model number {modelNumber} suggests more than 16 channels')
            sys.exit(1)
    if C_.scopeSeries == 'MSO':
        try:
            C_.scope.clear()
            print("Instrument buffer cleared successfully.")
        except Exception as e:
            print(f"An error occurred during clearing the buffer: {e}")
            sys.exit(1)

#``````````````````````````````````````````````````````````````````````````````
def handle_exception(where):
    """Handle exception"""
    #print('handle_exception',sys.exc_info())
    exceptionText = str(sys.exc_info()[1])
    tokens = exceptionText.split()
    msg = tokens[0] if tokens[0] == 'VI_ERROR_TMO' else exceptionText
    msg = msg+': '+where
    printw(msg)
    if True:# with Lock:
        C_.scope.write('*CLS')
    return -1

def adopt_local_setting():
    """Read scope setting and update PVs."""
    printi('adopt_local_setting: reading scope settings...')
    nothingChanged = True
    if True:#try:
        #print(f"adopt_local_setting: readSettingQuery: {C_.readSettingQuery}")
        if True:# with Lock:
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
            print(f'adopt_local_setting: {parname}={v}')
            publish(parname, v, IF_CHANGED)
        # special case of TrigLevel
        if True:# with Lock:
            if (cmd := trigLevelCmd()):
                value = C_.scope.query(cmd  +'?')
                publish('trigLevel', value, IF_CHANGED)
    else:#except:
        handle_exception(f'in adopt_local_setting {parname}={v}')
        return
    if nothingChanged:
        printi('Local setting did not change.')

#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````Acquisition-related functions`````````````````````````````````
def trigger_is_detected():
    """check if scope was triggered"""
    #print('Checking if trigger is detected...')
    ts = timer()
    try:
        r = query(['trigState','scopeAcqCount'],
                    ['DATa:SOUrce:AVAILable'])
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
        trigstate,numacq,*_ = r#,channelsEnabled = r
    except Exception as e:
        printw(f'wrong trig info: {r}, exception:{e}')
        return False
    #print(f'trigger_is_detected: trigState={trigstate}, numacq={numacq}')
    if not trigstate.startswith('TRIG'):
        #printw(f'Unexpected trigger state: {trigstate}')
        return False

    numacq = int(numacq)
    #print(f'Trigger check: trigState={trigstate}, numacq={numacq}, recLengthR={rl}, timePerDiv={timePerDiv}')
    if numacq == 0 or C_.numacq == 0:
        C_.triggersLost = 0
    else:
        C_.triggersLost += numacq - C_.numacq - 1
    C_.triggersLost = max(C_.triggersLost, 0)
    if numacq <= C_.numacq:
        if numacq == C_.numacq:
            publish('status',f'WAR: Scope not acquiring. numacq={numacq}, C_.numacq={C_.numacq}')
        else:
            printw('Scope acquisition count was reset. Something changed in the scope settings.')
        C_.numacq = numacq
        return False

    # trigger detected
    #print(f'Trigger detected: trigState={trigstate}, numacq={numacq}, recLengthR={rl}, timePerDiv={timePerDiv}')
    C_.numacq = numacq
    C_.trigTime = time.time()
    d = {'trigState':trigstate}
    for pvname,value in d.items():
        publish(pvname, value, IF_CHANGED, t=C_.trigTime)
    ElapsedTime['trigger_detection'] = round(timer()-ts,6)
    printv(f'Trigger detected {C_.numacq}')
    return True

def trigLevelCmd():
    """Generate SCPI command for trigger level control"""
    ch = str(pvv('trigSource'))
    if ch[:2] != 'CH':
        return None
    r = 'TRIGger:A:LEVel:'+ch
    #print(f'tlcmd: {r}')
    return r

#``````````````````Acquisition-related functions``````````````````````````````
def _acquire(startStop = 'Start'):
    """Start or stop acquisition"""
    if startStop == 'Stop':
        C_.scope.write(':ACQuire:STATE STOP')
        #printi('Acquisition stopped')
    else:
        C_.scope.write(':ACQuire:STATE RUN')
        #printi('Acquisition started')

def acquire_waveforms():
    """Acquire waveforms from the device and publish them."""
    #_acquire('Stop')  # Stop acquisition to ensure we get the latest data
    refresh_channelsEnabled()
    channels = C_.channelsEnabled
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
            if True:# with Lock:
                C_.scope.write(f'DATa:SOUrce CH{ch}')
            dt = timer() - ts
            ts = timer()
            #printvv(f'aw preamble{ch}: ymult={C_.ymult[ch]}, yoff={C_.yoff[ch]}, yzero={C_.yzero[ch]}, dt: {dt}')
            ElapsedTime['preamble'] += dt

            # acquire the waveform
            operation = 'getting waveform'
            try:
                if True:# with Lock:
                    bin_wave = C_.scope.query_binary_values('curve?',
                        datatype='h', is_big_endian=BigEndian,
                        container=np.array)
            except Exception as e:
                printe(f'in query_binary_values: {e}')
                break
            ElapsedTime['query_wf'] += timer() - ts
            ts = timer()

            # Convert to vertical divisions
            yincr, yoffset, yzero, voltsPerDiv = C_.prevYpreamble[ch-1]
            printv(f'Channel {ch}: yincr={yincr}, yoffset={yoffset}, yzero={yzero}, voltsPerDiv={voltsPerDiv}')
            samplesv = (bin_wave - yoffset) * yincr + yzero# Convert to volts
            printv(f'max,min: {samplesv.max(),samplesv.min()}')
            voffset = pvv(f'c{ch:02}Offset')
            samplesd = (samplesv/voltsPerDiv + voffset).astype(np.float32)  # Convert to divisions

            # publish
            operation = 'publishing'
            publish(f'c{ch:02}Waveform', samplesd, t=C_.trigTime)
            publish(f'c{ch:02}Peak2Peak', np.ptp(samplesv), t=C_.trigTime)
            publish(f'c{ch:02}Mean', np.mean(samplesv), t=C_.trigTime)
            publish(f'c{ch:02d}RMS', float(np.std(samplesv)), t=C_.trigTime)
            publish(f'c{ch:02d}Min', float(np.min(samplesv)), t=C_.trigTime)
        except visa.errors.VisaIOError as e:
            printe(f'Visa exception in {operation} for {ch}:{e}')
            break
        except Exception as e:
            printe(f'Exception in processing channel {ch}: {e}')
        ElapsedTime['publish_wf'] += timer() - ts
    ElapsedTime['acquire_wf'] = timer() - ElapsedTime['acquire_wf']
    #print(f'elapsedTime: {ElapsedTime}')
    #_acquire('Start')  # Restart acquisition after reading waveforms

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
    publish('scopeIDN', C_.idn)
    make_readSettingQuery()
    adopt_local_setting()
    _acquire('Start')

def periodicUpdate():
    """Called for infrequent updates"""
    printv('>periodicUpdate')
    try:
        update_scopeParameters()
        r = scopeCmd(':DATE?;:TIMe?;:ACQ:STATE?').split(';')
        dt = ' '.join(r[1:2]).replace('"','')
        #print(f'dateTime: {dt}, {r}')
        publish('dateTime', dt)
        publish('scopeAcqCount', C_.numacq, IF_CHANGED)
        publish('lostTrigs', C_.triggersLost, IF_CHANGED)
        #publish('actOnEvent', r[0], IF_CHANGED)
        if r[2] != '0':# Acquisition not stopped
            publish('timing', [(round(i,6)) for i in ElapsedTime.values()])
    except KeyboardInterrupt:
        raise
    except Exception:
        handle_exception('in periodic_update')
    printv('<periodicUpdate')

def poll():
    """Instrument polling function"""
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
    parser.add_argument('-C', '--channels', type=int, help=
    'Number of channels per device, if not given, then it is determined from the device model')
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
    printv(f'pargs: {pargs}')

    init_visa()  # Initialize VISA and determine the number of channels if not provided
    printi(f'Number of channels determined: {pargs.channels}')
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
    try:
        while True:
            state = serverState()
            if state.startswith('Exit'):
                break
            if not state.startswith('Stop'):
                poll()
            if not sleep():
                periodicUpdate()
    except KeyboardInterrupt:
        printi('Keyboard interrupt received, exiting main loop...')
        set_server('Exit')
    printi('Server is exited')
