# Accelerator DMA Security Validation

This document describes the security validation infrastructure for preventing confused deputy attacks on shared edge AI accelerators in gem5-SALAM.

## Overview

When multiple processes share a hardware accelerator, there's a risk that a malicious process could trick the accelerator into accessing memory belonging to another process (confused deputy attack). This infrastructure validates DMA addresses before accelerator commands execute, ensuring process isolation.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CPU Process                              │
│   ┌─────────────┐                     ┌──────────────────┐      │
│   │ Page Tables │──────mmu_notifier───│ AcceleratorContext│      │
│   │   (CPU)     │      callback       │    Manager       │      │
│   └─────────────┘                     └────────┬─────────┘      │
└────────────────────────────────────────────────┼────────────────┘
                                                 │
                                                 ▼
                              ┌──────────────────────────────┐
                              │   AcceleratorPageTable       │
                              │  ┌────────────────────────┐  │
                              │  │  IOTLB (64 entries)    │  │
                              │  │  - 3 cycle hit         │  │
                              │  │  - LRU replacement     │  │
                              │  └────────────────────────┘  │
                              │  ┌────────────────────────┐  │
                              │  │  4-Level Page Table    │  │
                              │  │  - 50 cycles/level     │  │
                              │  │  - 200 cycle miss      │  │
                              │  └────────────────────────┘  │
                              │  ┌────────────────────────┐  │
                              │  │  Page Pinning          │  │
                              │  │  - 256 pages/process   │  │
                              │  │  - 10ms timeout        │  │
                              │  └────────────────────────┘  │
                              └──────────────┬───────────────┘
                                             │
                              ┌──────────────┴───────────────┐
                              │                              │
                    ┌─────────▼──────────┐    ┌─────────────▼──────────┐
                    │  NoncoherentDma    │    │      StreamDma         │
                    │  validateAccess()  │    │   validateAccess()     │
                    └────────────────────┘    └────────────────────────┘
```

## Components

### AcceleratorPageTable

4-level ARM-style page table with IOTLB caching:

| Parameter | Default | Description |
|-----------|---------|-------------|
| page_size | 4KB | Page size (ARM default) |
| iotlb_entries | 64 | Number of IOTLB entries |
| iotlb_hit_latency | 3 cycles | IOTLB hit latency |
| walk_latency_per_level | 50 cycles | Per-level walk latency |
| invalidate_base_cycles | 50 cycles | Base invalidation cost |
| pin_latency | 50 cycles | Page pin latency |
| max_pin_duration_cycles | 10M cycles | Max pin time (~10ms at 1GHz) |
| max_pinned_pages_per_process | 256 | Max pinned pages (1MB) |

### AcceleratorContextManager

Per-process isolation with lazy context switching:

| Parameter | Default | Description |
|-----------|---------|-------------|
| context_switch_latency | 1500 cycles | Context switch cost (IOTLB flush) |

### AccelMmuNotifier

Global singleton for CPU→Accelerator page table synchronization:
- Receives callbacks when CPU unmaps memory
- Propagates invalidations to all registered accelerator contexts
- Handles deferred invalidations for pinned pages

## Performance Characteristics

### Typical Workload Costs

| Operation | Cost | Notes |
|-----------|------|-------|
| IOTLB hit | 3 cycles | Most DMA accesses |
| IOTLB miss (full walk) | 200 cycles | 4×50 cycles |
| Context switch | 1500 cycles | Only on PID change |
| Batch invalidation | 50 + 10×N cycles | N = number of pages |
| Page pin | 50 cycles | get_user_pages semantics |

### Expected Overhead (MobileNetV2)

Based on typical edge AI workload patterns:
- ~5-10% overhead for address validation
- ~95%+ IOTLB hit rate with 64 entries
- Minimal context switch overhead with lazy switching

## Usage

### Basic Setup

```python
from m5.objects import *

# Create security components
page_table = AcceleratorPageTable()
context_mgr = AcceleratorContextManager()
context_mgr.setPageTable(page_table)

# Attach to system
system.accel_page_table = page_table
system.accel_context_mgr = context_mgr

# Configure DMA with security
system.dma.setSecurityContext(context_mgr)
system.dma.setProcessId(process_pid)
```

### Register Process Mappings

```python
# Register process
context_mgr.registerProcess(pid)

# Map memory regions
context_mgr.mapForProcess(pid, vaddr=0x80000000, paddr=0x80000000, 
                          size=0x1000000, writable=True)
```

### Debug Output

Enable debug flags to see security validation:

```bash
./build/ARM/gem5.opt --debug-flags=AccelPageTable,AccelContext,AccelMmuNotifier ...
```

## Statistics

The following statistics are collected:

### AcceleratorPageTable
- `iotlbHits` / `iotlbMisses`: IOTLB hit rate
- `pageTableWalks` / `walkCycles`: Page table walk overhead
- `batchInvalidations` / `pagesInvalidated` / `invalidationCycles`: Invalidation costs
- `pagesPinned` / `pagesUnpinned` / `pinCycles`: Page pinning overhead
- `deferredInvalidations`: Invalidations delayed due to pinned pages
- `pinTimeouts` / `pinLimitExceeded`: Pin limit enforcement

### AcceleratorContextManager
- `contextSwitches` / `contextSwitchCycles`: Context switch overhead
- `lazySwitchesAvoided`: Lazy switch optimization hits
- `mmuNotifierCalls`: CPU→Accelerator sync events
- `accessValidations` / `accessDenied`: Security check results

## Security Model

1. **Log-only mode**: Violations are logged but don't halt execution (research focus)
2. **Per-process isolation**: Each process has separate page table context
3. **mmu_notifier sync**: CPU page table changes propagate to accelerator
4. **Page pinning**: DMA buffers pinned during transfer (get_user_pages semantics)
5. **Deferred invalidation**: Pinned pages invalidated after unpin

## Files

| File | Description |
|------|-------------|
| `src/hwacc/accelerator_page_table.hh/cc` | Page table + IOTLB implementation |
| `src/hwacc/accelerator_context.hh/cc` | Context manager implementation |
| `src/hwacc/accel_mmu_notifier.hh/cc` | MMU notifier singleton |
| `src/hwacc/AcceleratorPageTable.py` | Python SimObject binding |
| `src/hwacc/AcceleratorContextManager.py` | Python SimObject binding |
| `configs/SALAM/accel_security_config.py` | Sample configuration |

## Building

The security validation code is automatically built when ARM target is enabled:

```bash
scons build/ARM/gem5.opt -j$(nproc)
```

## Future Work

1. Add blocking mode (fault on violation instead of log)
2. Hardware cost estimation for ASIC implementation
3. Multi-accelerator support
4. Integration with SMMU for hybrid validation
