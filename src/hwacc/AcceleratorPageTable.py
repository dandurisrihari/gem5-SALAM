from m5.params import *
from m5.proxy import *
from m5.SimObject import SimObject
from m5.objects.ClockedObject import ClockedObject

class AcceleratorPageTable(ClockedObject):
    """
    Accelerator Page Table with IOTLB for edge AI security validation.

    Implements a 4-level ARM-style page table with:
    - 64-entry IOTLB with LRU replacement
    - Page pinning for DMA (get_user_pages semantics)
    - Batch invalidation (mmu_notifier style)
    - Per-process isolation

    Used to validate DMA addresses before accelerator commands execute,
    preventing confused deputy attacks on shared accelerators.
    """
    type = 'AcceleratorPageTable'
    cxx_header = 'hwacc/accelerator_page_table.hh'
    cxx_class = 'gem5::AcceleratorPageTable'

    # Page size (default 4KB for ARM)
    page_size = Param.MemorySize('4KiB', 'Page size')

    # IOTLB configuration
    iotlb_entries = Param.UInt32(64, 'Number of IOTLB entries')
    iotlb_hit_latency = Param.Cycles(3, 'IOTLB hit latency in cycles')

    # Page table walk latency (per level)
    walk_latency_per_level = Param.Cycles(50,
        'Page table walk latency per level (4 levels total)')

    # Invalidation timing
    invalidate_base_cycles = Param.Cycles(50,
        'Base cycles for invalidation (plus 10 per page)')

    # Page pinning configuration
    pin_latency = Param.Cycles(50, 'Latency for page pin operation')
    max_pin_duration_cycles = Param.Tick(10000000,
        'Maximum duration a page can be pinned (~10ms at 1GHz)')
    max_pinned_pages_per_process = Param.UInt32(256,
        'Maximum pages pinned per process (256 = 1MB with 4KB pages)')
