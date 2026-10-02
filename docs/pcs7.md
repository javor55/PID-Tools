# Implementation in PCS 7

How to transfer results from PID Tools to SIMATIC PCS 7 with the APL library. Each APC structure in the app has
a guide with concrete values for your loop – this is an overview.

> Parameter and input names of blocks may differ between APL versions. Check them in the documentation of your
> library version. The parameters are model-based proposals – introduce them gradually and verify on the plant.

---

## PIDConL controller

| In the app | In PCS 7 | Note |
|---|---|---|
| Controller range **NormPV / NormMV** | scaling ranges of PV and MV of the block | must match the block – Gain is scaled by them |
| **Gain, TI, TD** (Set 2) | Gain, TI, TD | ideal form, Gain dimensionless; negative Gain = reverse action |
| **DiffGain** | DiffGain (faceplate *Derivative gain*) | D filter TD/DiffGain |
| **P / D on feedback** | PropFacSP = 0 / DiffToFbk = 1 (otherwise PropFacSP = 1, DiffToFbk = 0) | P or D from PV only – smaller MV kick on SP changes |
| **SampleTime** | cycle of the OB the block runs in | the proposals take it into account |
| **MV_LoLim / MV_HiLim** | MV_LoLim / MV_HiLim | in MV units |
| **Deadband** | DeadBand | in PV units |
| Control zone | ConZone | only for gain scheduling by ER / comparison |
| Feedforward | FFwd, FFwdHiLim, FFwdLoLim | see below |

**Procedure:** enter the current faceplate parameters into *Set 1*; the new proposal is in *Set 2*. The parameter
table in Tuning and the section *PIDConL controller parameters* of the tuning protocol list the original and new
values. Enter parameters in the faceplate or in CFC; read changes made online back into the ES so they stay in the
offline data.

---

## APC templates (Templates › Control)

| Structure | Template / blocks | What the app provides |
|---|---|---|
| **Cascade** | **CascadeControl** – two PIDConL (+ ConPerMon) | Gain/TI of the inner and outer loop, check of speed separation |
| **Feedforward** | **FfwdDisturbCompensat** – gain, LeadLag, DeadTime → input **FFwd** | gain in MV units, lead, lag, delay, FFwd limits |
| **Decoupling** | decoupler = feedforward per **FfwdDisturbCompensat**, the disturbance is the MV of the other loop | gain, lead-lag and delay of each decoupler |
| **Override** | **OverrideControl** – two PIDConR, selector **SelA02In**, external reset (**ExtReset**, **ExtResOn**) | MIN/MAX selection, limit, parameters of both controllers |
| **Smith predictor** | **SmithPredictorControl** – Lag, Mul04, Add04 (PV0), DeadTime | LagTime, gain in engineering units, PV0 offset, DeadTime, Gain/TI |
| **Gain scheduling** | **GainScheduling** – block **GainSched** + PIDConL | X1…X3, Gain1…3, TI1…3, TD1…3 (by PV or ER) |

### Cascade
1. Connect the MV of the outer controller to the external setpoint **SP_Ext** of the inner one; the MV range of the
   outer controller = the PV range of the inner one.
2. Tune and put the inner loop into auto first, then the outer one.

### Feedforward
1. Route the measured disturbance through the gain, optionally **LeadLag** and **DeadTime**, to input **FFwd** of the
   controller. FFwd is added to the output in **MV units** – the app gives the gain in these units.
2. Send the **deviation of the disturbance from its operating value**, not the absolute value – otherwise MV jumps
   when FF is switched on.
3. Limit the contribution with **FFwdHiLim / FFwdLoLim**.
4. Commission with 50–80 % of the proposed gain; switch FF off when the disturbance measurement fails.

The controller is not tuned differently because of feedforward – it does not change the stability of the loop.

### Decoupling
Each decoupler is feedforward from the MV of the other loop (change from the operating point × gain, through
lead-lag and delay). When the other loop is in manual, switch the decoupler off.

### Override
1. Outputs of both controllers into **SelA02In**, the selected value to the valve.
2. Feed the selected MV back to **ExtReset** of both controllers and switch on **ExtResOn** – the inactive controller
   does not wind up.
3. SP of the limiting controller = the limit.

### Smith predictor
Following the Siemens application example *Smith Predictor for Control of Processes with Dead Times*
(entry 37361207):
1. Input PIDConL.PV is already connected to the virtual dead-time-free PV in the template – do not connect it to the
   periphery.
2. Predictor model in **engineering units**: `SmithModelTimLag.LagTime`, `SmithModelGain.In2`,
   `SmithModelDeadti.DeadTime`. A second-order model is entered as the sum time constant.
3. Offset **PV0** (Add04 block before DeadTime) = steady-state PV at MV = 0; mandatory for a negative gain.
4. To identify a loop that already has a predictor, take PV from `Pcs7AnIn.PV_Out`, not `PIDConL.PV`.
5. Verify the dead time with a step; rather round it up (an underestimated θ leads to oscillation).

### Gain scheduling
Following the Siemens application example *PID Tuning with Gain Scheduling* (entry 38755162):
1. **By PV:** input `X` is connected to PV in the template; enter the values from the app into `X1…X3`,
   `Gain1…3`, `TI1…3`, `TD1…3`. The PID Tuner cannot download parameters into the scheduler – enter them in CFC or
   in the GainSched faceplate.
2. **By ER:** connect `X` to output `ER` of the controller; points −E, 0, +E, `Gain1 = Gain3 = k × Gain`, TI and TD
   the same. Verify a bumpless Gain change and that the loop does not oscillate at full gain.
3. Gain, TI, TD of PIDConL are then driven by the scheduler; for special situations GainSched can be switched to
   manual.

---

## Data from PCS 7 and the historian

- **CFC Trend Display** – export to CSV (default separators); for identification record PV from the driver
  `Pcs7AnIn.PV_Out` and the controller MV.
- **Process Historian / WinCC** – export tags to CSV / Excel; the app handles common time, a time per variable and
  long format (tag, time, value), including UTF-16 encoding.
- For identification ask for **uncompressed** data (no archive deadband) with a period at least 10× shorter than the
  process time constant.
