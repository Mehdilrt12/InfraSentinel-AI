from types import SimpleNamespace
from unittest import TestCase

from tests.load import controlled_cpu_load as cpu
from tests.load import controlled_gpu_load as gpu


class CpuSafetyValidationTests(TestCase):
    def args(self, **overrides):
        values = {
            "api_url": "http://127.0.0.1:8000/api/health/",
            "workers": 16,
            "duration": 45,
            "max_cpu_percent": 85,
            "gpu_stop_temperature": 85,
            "label": "CONTROLLED_TEST_CPU",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_accepts_bounded_loopback_stage(self):
        cpu.validate(self.args())

    def test_rejects_public_target(self):
        with self.assertRaises(SystemExit):
            cpu.validate(self.args(api_url="https://example.com/api/health/"))

    def test_rejects_worker_and_duration_over_caps(self):
        with self.assertRaises(SystemExit):
            cpu.validate(self.args(workers=25))
        with self.assertRaises(SystemExit):
            cpu.validate(self.args(duration=46))

    def test_requires_controlled_marker(self):
        with self.assertRaises(SystemExit):
            cpu.validate(self.args(label="unmarked"))


class GpuSafetyValidationTests(TestCase):
    def args(self, **overrides):
        values = {
            "api_url": "http://localhost:8000/api/health/",
            "mode": "compute",
            "duration": 20,
            "duty_cycle": 0.7,
            "vram_fraction": 0.25,
            "matrix_size": 3072,
            "stop_temperature": 78,
            "label": "CONTROLLED_TEST_GPU",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_accepts_bounded_compute_stage(self):
        gpu.validate(self.args())

    def test_rejects_compute_duty_over_cap(self):
        with self.assertRaises(SystemExit):
            gpu.validate(self.args(duty_cycle=0.76))

    def test_rejects_vram_fraction_over_cap(self):
        with self.assertRaises(SystemExit):
            gpu.validate(self.args(mode="vram", duration=8, vram_fraction=0.51))

    def test_rejects_non_loopback_target(self):
        with self.assertRaises(SystemExit):
            gpu.validate(self.args(api_url="http://192.0.2.10:8000/api/health/"))
