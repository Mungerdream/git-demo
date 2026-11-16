# virtual clock: EPFL designs are pure combinational, there is no clock pin to
# constrain, so all I/O is referenced to a virtual 100 ns clock.  The period is
# loose on purpose -- a 128-bit ripple adder cannot close at 10 ns in sky130 and
# a failing timing repair would inflate area for reasons unrelated to the
# library under test.  Timing is recorded as a guard rail, not as an objective.
create_clock -name vclk -period 100

set_input_delay  -clock vclk 0 [all_inputs]
set_output_delay -clock vclk 0 [all_outputs]
set_load 5 [all_outputs]
