# PID Tools (PIDConL Tuner)

**PID Tools** is an interactive web application built with Python (using the Streamlit framework). It is designed for process model identification from real measured data and advanced tuning of PID controllers. The application is primarily tailored for analyzing and tuning the **PIDConL** block structure in the **SIMATIC PCS 7 APL** control system, but its underlying principles and calculations can be successfully applied to other industrial controllers.

## 🚀 What is this application for?
- **System Identification:** Automatically calculates a mathematical process model from operational data (e.g., following a step change in the manipulated variable). It supports both self-regulating and integrating processes with dead time.
- **Controller Tuning:** Based on the identified model, the application suggests ideal PID controller parameters (Gain, TI, TD) using selected tuning methodologies (SIMC, Lambda, AMIGO, etc.).
- **Simulation and Robustness:** Allows you to simulate the control loop behavior before actual deployment in PCS 7, check robustness (maximum sensitivity Ms, phase and gain margins), and tune the behavior under disturbances or valve stiction.

## ✨ Main Features
- **Flexible Data Processing:** Upload measured data from CSV or Excel (e.g., exported from WinCC / PCS 7 trends). Users can interactively select data segments, apply smoothing (high-pass filter to remove drift), and normalize the ranges of process (PV) and manipulated (MV) variables.
- **Models with Dead Time:**
  - `P0D`: 0th order (gain + dead time)
  - `P1D`: 1st order + dead time (FOPDT)
  - `P2D`: 2nd order + dead time (SOPDT)
  - `I0D`: Integrating + dead time
  - `I1D`: Integrating + 1st order + dead time
- **Model Quality Assessment:** Calculates model fit (FIT %), IAE (Integral Absolute Error), residual analysis, and autocorrelation to verify that the model captures all essential dynamics.
- **Tuning:** Calculates recommended parameters using algorithms like Skogestad's method (SIMC), Lambda tuning, or AMIGO, while accounting for the impact of the controller's discrete sampling time.
- **Closed-Loop Simulator (PIDConL):** A full feedback simulation implementing the specific features of the industrial PIDConL block:
  - PV filtering.
  - Deadband.
  - Rate limits and clamping for MV and Setpoint (Ramping).
  - Anti-windup integrator protection and bumpless transfers.
  - Simulation of valve hysteresis and stiction.
- **Bilingual Interface:** The application is fully localized in English and Czech.
- **Project Saving:** Save and load your settings (tuning state) in a single JSON file, allowing for easy later review or sharing of tuning reports.

## 🛠 How it works and how to run it
The application runs entirely locally in your browser and is powered by Python. It does not require installing any complex web server.

### Prerequisites
- Python 3.9 or higher installed.
- Basic familiarity with the command line is recommended, although a startup script is provided.

### Installation and Execution (Windows)
1. **Quick Start (Recommended):**
   Simply run the **`start.bat`** batch file in the root folder. 
   This script will automatically install any missing libraries from the `requirements.txt` file and launch the application immediately.
2. **Manual Start (via Command Line):**
   Open a terminal in the application folder and run:
   ```bash
   pip install -r requirements.txt
   streamlit run pid_app.py
   ```
3. The application will then open in your default web browser (typically at `http://localhost:8501`).

## 📖 Workflow
1. **Data Loading (Data):** Open the application and upload a data file using the top menu. Assign the correct columns for timestamp, PV, MV, and optionally SP. Then, select a suitable data segment in the chart capturing the response to an MV step change.
2. **Identification (Model):** In the model tab, select the expected process structure (e.g., P1D for common overdamped processes) and let the algorithm find the coefficients. You can also enable valve stiction estimation.
3. **Configuration and Tuning (Tuning):** Enter the existing control block parameters (sampling time, limits, or current PI parameters for comparison). Then specify the desired tuning aggressiveness (tau_c). The application will propose the ideal parameters.
4. **Verification (Simulation):** Test the proposed parameters and compare the behavior of the newly designed controller with the current (original) solution. Check loop robustness to ensure stability.
5. **Saving (Project):** Save the result and export your report / recommended parameters to PCS 7.

## ⚙️ Technologies Used
- **[Streamlit](https://streamlit.io/):** For building the visual, interactive user interface directly in Python.
- **[Plotly](https://plotly.com/python/):** For advanced charting with zoom and pan support.
- **[SciPy] & [NumPy]:** The numerical and optimization core (least-squares fit, discrete filters, etc.).
- **[Pandas]:** For manipulating tabular and time-series data.
