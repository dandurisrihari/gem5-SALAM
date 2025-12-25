#include "hwacc/accelerator_context.hh"

#include "base/logging.hh"
#include "base/trace.hh"
#include "debug/AccelContext.hh"
#include "hwacc/accel_mmu_notifier.hh"

namespace gem5
{

AcceleratorContextManager::AcceleratorContextManager(const Params &p)
    : ClockedObject(p),
      stats(this),
      contextSwitchLatency(p.context_switch_latency),
      pageTable(nullptr),
      currentPid(0)
{
    DPRINTF(AccelContext, "AcceleratorContextManager created: "
            "contextSwitchLatency=%d cycles\n", contextSwitchLatency);

    // Register with the global MMU notifier
    AccelMmuNotifier::getInstance().registerContext(this);
}

AcceleratorContextManager::~AcceleratorContextManager()
{
    // Unregister from the global MMU notifier
    AccelMmuNotifier::getInstance().unregisterContext(this);
}

void
AcceleratorContextManager::registerProcess(uint64_t pid)
{
    if (contexts.find(pid) != contexts.end()) {
        DPRINTF(AccelContext, "registerProcess: pid %llu already registered\n",
                pid);
        return;
    }

    DPRINTF(AccelContext, "registerProcess: pid %llu\n", pid);
    contexts[pid] = AcceleratorContext(pid);
    stats.processesRegistered++;
}

void
AcceleratorContextManager::deregisterProcess(uint64_t pid)
{
    auto it = contexts.find(pid);
    if (it == contexts.end()) {
        DPRINTF(AccelContext, "deregisterProcess: pid %llu not found\n", pid);
        return;
    }

    DPRINTF(AccelContext, "deregisterProcess: pid %llu\n", pid);

    // If this was the current context, switch away
    if (currentPid == pid) {
        currentPid = 0;
        if (pageTable) {
            pageTable->flushIOTLB();
        }
    }

    contexts.erase(it);
    stats.processesDeregistered++;
}

Cycles
AcceleratorContextManager::switchContext(uint64_t pid)
{
    if (currentPid == pid) {
        // Same context, no switch needed (lazy)
        stats.lazySwitchesAvoided++;
        DPRINTF(AccelContext, "switchContext: same pid %llu, no switch\n",
                pid);
        return Cycles(0);
    }

    // Check if process is registered
    auto it = contexts.find(pid);
    if (it == contexts.end()) {
        DPRINTF(AccelContext, "switchContext: pid %llu not registered, "
                "auto-registering\n", pid);
        registerProcess(pid);
    }

    DPRINTF(AccelContext, "switchContext: %llu -> %llu (%d cycles)\n",
            currentPid, pid, contextSwitchLatency);

    // Save current context (if any)
    if (currentPid != 0) {
        saveContext();
    }

    // Load new context
    currentPid = pid;
    loadContext(pid);

    // Flush IOTLB on context switch
    if (pageTable) {
        pageTable->flushIOTLB();
    }

    // Update access time
    contexts[pid].lastAccessTick = curTick();

    stats.contextSwitches++;
    stats.contextSwitchCycles += (uint64_t)contextSwitchLatency;

    return contextSwitchLatency;
}

void
AcceleratorContextManager::mapForProcess(uint64_t pid, Addr vaddr, Addr paddr,
                                          size_t size, bool writable)
{
    // Ensure process is registered
    if (contexts.find(pid) == contexts.end()) {
        registerProcess(pid);
    }

    DPRINTF(AccelContext, "mapForProcess: pid=%llu, vaddr=0x%lx, paddr=0x%lx, "
            "size=%d, writable=%d\n", pid, vaddr, paddr, size, writable);

    // Add to process-specific mappings
    AcceleratorContext &ctx = contexts[pid];
    Addr va = vaddr & ~(4095ULL);  // Page align
    Addr pa = paddr & ~(4095ULL);
    size_t numPages = (size + 4095) / 4096;

    for (size_t i = 0; i < numPages; i++) {
        (*ctx.mappings)[va] = AcceleratorPTE(pa, writable);
        va += 4096;
        pa += 4096;
    }

    // If this is the current process, also update the page table
    if (currentPid == pid && pageTable) {
        pageTable->map(vaddr, paddr, size, writable);
    }
}

void
AcceleratorContextManager::unmapForProcess(
    uint64_t pid, Addr vaddr, size_t size)
{
    auto it = contexts.find(pid);
    if (it == contexts.end()) {
        DPRINTF(AccelContext, "unmapForProcess: pid %llu not found\n", pid);
        return;
    }

    DPRINTF(AccelContext, "unmapForProcess: pid=%llu, vaddr=0x%lx, size=%d\n",
            pid, vaddr, size);

    // Remove from process-specific mappings
    AcceleratorContext &ctx = it->second;
    Addr va = vaddr & ~(4095ULL);  // Page align
    size_t numPages = (size + 4095) / 4096;

    for (size_t i = 0; i < numPages; i++) {
        ctx.mappings->erase(va);
        va += 4096;
    }

    // If this is the current process, also update the page table
    if (currentPid == pid && pageTable) {
        pageTable->unmap(vaddr, size);
    }
}

bool
AcceleratorContextManager::validateAccess(Addr vaddr, bool isWrite)
{
    stats.accessValidations++;

    if (currentPid == 0) {
        DPRINTF(AccelContext, "validateAccess: no context set, denying\n");
        stats.accessDenied++;
        return false;
    }

    if (!pageTable) {
        DPRINTF(AccelContext, "validateAccess: no page table, denying\n");
        stats.accessDenied++;
        return false;
    }

    bool result = pageTable->validateAccess(vaddr, isWrite);
    if (!result) {
        stats.accessDenied++;
        DPRINTF(AccelContext, "validateAccess: pid=%llu, vaddr=0x%lx, "
                "isWrite=%d -> DENIED\n", currentPid, vaddr, isWrite);
    } else {
        DPRINTF(AccelContext, "validateAccess: pid=%llu, vaddr=0x%lx, "
                "isWrite=%d -> ALLOWED\n", currentPid, vaddr, isWrite);
    }

    return result;
}

void
AcceleratorContextManager::mmuNotifierInvalidate(uint64_t pid,
                                                  Addr startVa, Addr endVa)
{
    DPRINTF(AccelContext, "mmuNotifierInvalidate: pid=%llu, va=0x%lx-0x%lx\n",
            pid, startVa, endVa);

    stats.mmuNotifierCalls++;

    if (pid == 0) {
        // Invalidate for all processes
        for (auto &pair : contexts) {
            Addr va = startVa & ~(4095ULL);
            while (va < endVa) {
                pair.second.mappings->erase(va);
                va += 4096;
            }
        }

        // Also invalidate in the active page table
        if (pageTable) {
            pageTable->invalidateRange(startVa, endVa);
        }
    } else {
        // Invalidate for specific process
        auto it = contexts.find(pid);
        if (it != contexts.end()) {
            Addr va = startVa & ~(4095ULL);
            while (va < endVa) {
                it->second.mappings->erase(va);
                va += 4096;
            }

            // If this is the current process, also invalidate in page table
            if (currentPid == pid && pageTable) {
                pageTable->invalidateRange(startVa, endVa);
            }
        }
    }
}

void
AcceleratorContextManager::loadContext(uint64_t pid)
{
    auto it = contexts.find(pid);
    if (it == contexts.end() || !pageTable) {
        return;
    }

    DPRINTF(AccelContext, "loadContext: loading %d mappings for pid %llu\n",
            it->second.mappings->size(), pid);

    // Load all mappings into the page table
    for (const auto &pair : *it->second.mappings) {
        pageTable->map(pair.first, pair.second.paddr,
                       4096, pair.second.writable);
    }
}

void
AcceleratorContextManager::saveContext()
{
    // In this simplified implementation, context is already saved in the
    // per-process mappings structure, so no action needed.
    // A more complex implementation might copy page table state back.
    DPRINTF(AccelContext, "saveContext: saving context for pid %llu\n",
            currentPid);
}

// Statistics
AcceleratorContextManager::ContextStats::ContextStats(
    AcceleratorContextManager *parent)
    : statistics::Group(parent),
      ADD_STAT(contextSwitches, statistics::units::Count::get(),
               "Number of context switches"),
      ADD_STAT(contextSwitchCycles, statistics::units::Cycle::get(),
               "Total cycles spent in context switches"),
      ADD_STAT(lazySwitchesAvoided, statistics::units::Count::get(),
               "Number of lazy switches avoided (same pid)"),
      ADD_STAT(processesRegistered, statistics::units::Count::get(),
               "Number of processes registered"),
      ADD_STAT(processesDeregistered, statistics::units::Count::get(),
               "Number of processes deregistered"),
      ADD_STAT(mmuNotifierCalls, statistics::units::Count::get(),
               "Number of mmu_notifier callbacks"),
      ADD_STAT(accessValidations, statistics::units::Count::get(),
               "Number of access validations"),
      ADD_STAT(accessDenied, statistics::units::Count::get(),
               "Number of access denials")
{
}

} // namespace gem5
