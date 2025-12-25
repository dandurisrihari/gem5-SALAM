from m5.params import *
from m5.proxy import *
from m5.SimObject import SimObject
from m5.objects.ClockedObject import ClockedObject

class AcceleratorContextManager(ClockedObject):
    """
    Context Manager for per-process isolation on shared accelerator.

    Features:
    - Per-process page table contexts
    - Lazy context switching (only flush IOTLB on pid change)
    - Centralized mmu_notifier callback handling
    - Process registration/deregistration

    Works with AcceleratorPageTable to provide confused deputy
    attack prevention for shared edge AI accelerators.
    """
    type = 'AcceleratorContextManager'
    cxx_header = 'hwacc/accelerator_context.hh'
    cxx_class = 'gem5::AcceleratorContextManager'

    # Context switch latency (lazy - only incurred on actual pid change)
    context_switch_latency = Param.Cycles(1500,
        'Context switch latency in cycles (IOTLB flush + CR3 equivalent)')
