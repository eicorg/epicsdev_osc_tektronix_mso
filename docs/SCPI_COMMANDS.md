# Tektronix MSO SCPI Command Mapping

This document outlines the key SCPI command differences between RIGOL and Tektronix MSO oscilloscopes.

## Key Differences

### Horizontal (Timebase) Commands

| Function | RIGOL | Tektronix |
|----------|-------|-----------|
| Record Length | `ACQuire:MDEPth` | `HORizontal:RECOrdlength` |
| Sampling Rate | `ACQuire:SRATe` | `HORizontal:SAMPLERate` |
| Time/Division | `TIMebase:SCALe` | `HORizontal:SCAle` |
| Trigger Position | `TRIGger:POSition` | `HORizontal:POSition` |

### Channel Commands

| Function | RIGOL | Tektronix |
|----------|-------|-----------|
| Channel Display | `CHANnel<n>:DISPlay` | `CH<n>:STATE` |
| Channel Coupling | `CHANnel<n>:COUPling` | `CH<n>:COUPling` |
| Vertical Scale | `CHANnel<n>:SCALe` | `CH<n>:SCAle` |
| Vertical Offset | `CHANnel<n>:OFFSet` | `CH<n>:OFFSet` |
| Input Termination | Fixed (1M) | `CH<n>:TERmination` (1M or 50Ω) |

### Trigger Commands

| Function | RIGOL | Tektronix |
|----------|-------|-----------|
| Trigger Mode | `TRIGger:SWEep` (NORM/AUTO/SING) | `TRIGger:A:MODe` (AUTO/NORMAL/SINGLE) |
| Trigger Type | `TRIGger:MODE` | `TRIGger:A:TYPE` |
| Trigger Source | `TRIGger:EDGE:SOURce` | `TRIGger:A:EDGE:SOUrce` |
| Trigger Slope | `TRIGger:EDGE:SLOPe` (POS/NEG/RFALI) | `TRIGger:A:EDGE:SLOpe` (RISE/FALL/EITHER) |
| Trigger Level | `TRIGger:EDGE:LEVel` | `TRIGger:A:LEVel` |
| Trigger Status | `TRIGger:STATus` | `TRIGger:STATE` |
| Trigger Coupling | `TRIGger:COUPling` | `TRIGger:A:EDGE:COUPling` |
| Force Trigger | `TFORce` | `TRIGger FORCe` |

### Waveform Data Commands

| Function | RIGOL | Tektronix |
|----------|-------|-----------|
| Waveform Format | `:WAV:FORM WORD` | `DATa:ENCdg RIBinary` |
| Waveform Mode | `:MODE RAW` | - |
| Data Source | `:WAV:SOURce` | `DATa:SOUrce` |
| Query Waveform | `:WAV:DATA?` | `CURVe?` |
| X Increment | `:WAV:XINC?` | `WFMOutpre:XINcr?` |
| X Origin | `:WAV:XORigin?` | `WFMOutpre:XZEro?` |
| Y Increment | `:WAV:YINC?` | `WFMOutpre:YMUlt?` |
| Y Origin | `:WAV:YORigin?` | `WFMOutpre:YZEro?` |
| Y Reference | `:WAV:YREFerence?` | `WFMOutpre:YOFf?` |
| Number of Points | `POINts?` | `WFMOutpre:NR_Pt?` |

### Setup Commands

| Function | RIGOL | Tektronix |
|----------|-------|-----------|
| Save Setup | `SAVE:SETup <filename>` | `SAVe:SETUp` |
| Load Setup | `LOAD:SETUp <filename>` | `RECAll:SETUp` |

## Data Format Differences

### RIGOL
- Uses simple binary format (16-bit words)
- Data conversion: `v = (waveform - yorig - yref) * yincr`

### Tektronix
- Uses IEEE definite-length arbitrary block format
- Header format: `#<x><yyy><data>` where:
  - `x` = number of digits in `yyy`
  - `yyy` = number of data bytes
- Data conversion: `v = (waveform - yoff) * ymult + yzero`

## Implementation Notes

1. **Record Length**: Tektronix supports different values (1000, 10000, 100000, 1000000, 10000000)
2. **Trigger Types**: Tektronix uses EDGE, PULSE, LOGIC, BUS vs RIGOL's EDGE, PULS, SLOP, VID
3. **Channel Termination**: Tektronix supports switchable 1MΩ/50Ω, RIGOL is fixed at 1MΩ
4. **Trigger Slope Values**: Different naming (RISE/FALL vs POS/NEG)
5. **Binary Data Format**: Tektronix uses more complex header structure

## References
- [Tektronix 4-5-6 Series MSO Programmer Manual](https://download.tek.com/manual/4-5-6-Series-MSO-Programmer_077130524.pdf)
- Based on epicsdev_rigol_scope implementation
