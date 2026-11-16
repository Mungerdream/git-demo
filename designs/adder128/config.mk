# EPFL combinational benchmark: adder128 (128-bit ripple-carry adder)
# Logical area of the *basic* library run on this design matches the CellE
# baseline (1974.3 -> ... chain), so it is the continuity anchor of the study.
export DESIGN_NICKNAME = adder128
export DESIGN_NAME     = top
export PLATFORM        = sky130hd

export VERILOG_FILES   = /work/rtl/adder128.v
export SDC_FILE        = /work/designs/adder128/constraint.sdc

# the two numbers that must stay identical across libraries
export CORE_UTILIZATION = 50
export PLACE_DENSITY    = 0.65

# area-driven mapping: this study measures area, timing is only a guard rail
export ABC_AREA = 1

# pure combinational logic: no clock tree to build
export SKIP_CTS_REPAIR_TIMING = 0
