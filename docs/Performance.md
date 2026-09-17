#Performance

## MSO64B, TCPIP SOCKET inteface, firmware 2.10.5.1825
Summary: 1.3M Samples/s. (4*1e5 points in 0.3 s.)

Details for 100K float32 points, sleep 1.0 s:

- 2 Traces: timing[2] = 0.14 s, cycleTime=1.28 s
- 4 Traces: timing[2] = 0.30 s, cycleTime=1.5 s

## DPO2004B, USB interface, firmware 1.56. Slow, not reliable.
Summary: 77K Samples/s. (2*1e5 points in 2.6 s)

Details for 100K float32 points, sleep 1.0 s:

- 2 traces, cycleTime 3.6 s
### Issue
Occasinally scope times out and requires power cycle after that.

## DPO2004B, TCPIP INSTR interface. Reliable but very slow.
Summary: 30K Samples/s for 100K float32 points

Details for 100K float32 points, sleep 1.0 s:

- 2 Traces: timing[2] = 6.0 s, cycleTime = 10 s