"""Model selection is pure logic (no hardware needed to test it), so it's
the easiest and highest-value thing in this project to cover with tests.
"""

from hardware import choose_model


def test_big_gpu_gets_turbo():
    hw = {"gpu": {"name": "RTX 4070", "vram_mb": 12000}, "cpu_cores": 8, "ram_gb": 16}
    assert choose_model(hw).model == "large-v3-turbo"


def test_your_gpu_gets_medium():
    hw = {"gpu": {"name": "RTX 3070 Laptop", "vram_mb": 8192}, "cpu_cores": 16, "ram_gb": 34}
    assert choose_model(hw).model == "medium"
    assert choose_model(hw).device == "cuda"


def test_no_gpu_strong_cpu_gets_small():
    hw = {"gpu": None, "cpu_cores": 8, "ram_gb": 16}
    assert choose_model(hw).model == "small"


def test_no_gpu_weak_cpu_gets_tiny():
    hw = {"gpu": None, "cpu_cores": 2, "ram_gb": 4}
    assert choose_model(hw).model == "tiny"