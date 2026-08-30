# Controlled local load tools

`controlled_cpu_load.py` is a local-only, time-bounded CPU generator for the
authorized InfraSentinel validation laptop. It refuses public targets, runs at
below-normal priority, preserves Windows/NVIDIA protections, and records its
samples under `runtime/performance/`.

On the current laptop CPU package temperature is unavailable. Consequently the
tool caps a stage to 45 seconds and 24 workers, aborts at 85% observed CPU, and
must not be used to claim a temperature-validated 90–100% CPU test.

`controlled_gpu_load.py` uses an already-installed CUDA-enabled PyTorch. It
refuses a hot/busy baseline, limits compute duty cycle to 75%, limits synthetic
VRAM use to 50%, aborts on temperature/throttling/API/Docker/RAM guards, and
always releases CUDA tensors in `finally`.
