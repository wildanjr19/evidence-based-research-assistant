import ctypes
import sys
from ctypes import wintypes


def process_resources() -> dict:
    result = {
        "peak_working_set_bytes": None,
        "peak_private_commit_bytes": None,
        "cuda_initialized": False,
        "peak_torch_allocated_bytes": 0,
        "peak_torch_reserved_bytes": 0,
        "scope": "Current Python process lifetime; PyTorch allocator only for VRAM",
    }
    if sys.platform == "win32":

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                    "PrivateUsage",
                )
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if psapi.GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            result["peak_working_set_bytes"] = counters.PeakWorkingSetSize
            result["peak_private_commit_bytes"] = counters.PeakPagefileUsage
    torch = sys.modules.get("torch")
    if torch is not None and torch.cuda.is_initialized():
        result["cuda_initialized"] = True
        result["peak_torch_allocated_bytes"] = sum(
            torch.cuda.max_memory_allocated(i) for i in range(torch.cuda.device_count())
        )
        result["peak_torch_reserved_bytes"] = sum(
            torch.cuda.max_memory_reserved(i) for i in range(torch.cuda.device_count())
        )
    return result
