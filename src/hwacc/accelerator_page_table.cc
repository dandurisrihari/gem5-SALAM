#include "hwacc/accelerator_page_table.hh"

#include <algorithm>
#include <cassert>

#include "base/logging.hh"
#include "base/trace.hh"
#include "debug/AccelPageTable.hh"

namespace gem5
{

AcceleratorPageTable::AcceleratorPageTable(const Params &p)
    : ClockedObject(p),
      stats(this),
      pageSize(p.page_size),
      iotlbEntries(p.iotlb_entries),
      iotlbHitLatency(p.iotlb_hit_latency),
      walkLatencyPerLevel(p.walk_latency_per_level),
      invalidateCycles(p.invalidate_base_cycles),
      pinLatency(p.pin_latency),
      maxPinDuration(p.max_pin_duration_cycles),
      maxPinnedPerProcess(p.max_pinned_pages_per_process),
      iotlb(iotlbEntries),
      lruCounter(0)
{
    DPRINTF(AccelPageTable, "AcceleratorPageTable created: "
            "pageSize=%d, iotlbEntries=%d, iotlbHitLatency=%d, "
            "walkLatencyPerLevel=%d, maxPinDuration=%llu, maxPinned=%d\n",
            pageSize, iotlbEntries, iotlbHitLatency, walkLatencyPerLevel,
            maxPinDuration, maxPinnedPerProcess);
}

AcceleratorPageTable::~AcceleratorPageTable()
{
}

void
AcceleratorPageTable::map(Addr vaddr, Addr paddr, size_t size, bool writable)
{
    Addr va = pageAlign(vaddr);
    Addr pa = pageAlign(paddr);
    size_t numPages = (size + pageSize - 1) / pageSize;

    DPRINTF(AccelPageTable, "map: va=0x%lx, pa=0x%lx, sz=%d, wr=%d, np=%d\n",
            vaddr, paddr, size, writable, numPages);

    for (size_t i = 0; i < numPages; i++) {
        pageTable[va] = AcceleratorPTE(pa, writable);
        va += pageSize;
        pa += pageSize;
    }
}

void
AcceleratorPageTable::unmap(Addr vaddr, size_t size)
{
    Addr va = pageAlign(vaddr);
    size_t numPages = (size + pageSize - 1) / pageSize;

    DPRINTF(AccelPageTable, "unmap: va=0x%lx, sz=%d, np=%d\n",
            vaddr, size, numPages);

    for (size_t i = 0; i < numPages; i++) {
        auto it = pageTable.find(va);
        if (it != pageTable.end()) {
            // Cannot unmap pinned pages directly
            if (it->second.pinned) {
                DPRINTF(AccelPageTable,
                        "unmap: page 0x%lx is pinned, deferring\n", va);
                addDeferredInvalidation(va, va + pageSize);
            } else {
                pageTable.erase(it);
                flushIOTLBEntry(va);
            }
        }
        va += pageSize;
    }
}

bool
AcceleratorPageTable::lookup(Addr vaddr, Addr &paddr, bool &writable)
{
    Addr pageVa = pageAlign(vaddr);
    size_t offset = pageOffset(vaddr);

    // Try IOTLB first
    if (iotlbLookup(pageVa, paddr, writable)) {
        stats.iotlbHits++;
        paddr += offset;
        DPRINTF(AccelPageTable, "lookup IOTLB hit: va=0x%lx -> pa=0x%lx\n",
                vaddr, paddr);
        return true;
    }

    stats.iotlbMisses++;

    // Page table walk
    if (pageTableWalk(pageVa, paddr, writable)) {
        // Insert into IOTLB
        iotlbInsert(pageVa, paddr, writable);
        paddr += offset;
        DPRINTF(AccelPageTable, "lookup walk hit: va=0x%lx -> pa=0x%lx\n",
                vaddr, paddr);
        return true;
    }

    DPRINTF(AccelPageTable, "lookup miss: vaddr=0x%lx not mapped\n", vaddr);
    return false;
}

size_t
AcceleratorPageTable::invalidateRange(Addr startVa, Addr endVa)
{
    Addr va = pageAlign(startVa);
    Addr vaEnd = pageAlign(endVa + pageSize - 1);
    size_t numPagesInRange = (vaEnd - va) / pageSize;
    size_t invalidated = 0;
    size_t deferred = 0;

    DPRINTF(AccelPageTable, "invalidateRange: 0x%lx - 0x%lx (%d pages)\n",
            startVa, endVa, numPagesInRange);

    stats.batchInvalidations++;

    while (va < vaEnd) {
        auto it = pageTable.find(va);
        if (it != pageTable.end()) {
            if (it->second.pinned) {
                // Page is pinned, defer invalidation
                DPRINTF(AccelPageTable, "invalidateRange: page 0x%lx pinned, "
                        "deferring invalidation\n", va);
                addDeferredInvalidation(va, va + pageSize);
                deferred++;
                stats.deferredInvalidations++;
            } else {
                // Mark as invalid and flush IOTLB
                it->second.valid = false;
                flushIOTLBEntry(va);
                invalidated++;
            }
        }
        va += pageSize;
    }

    stats.pagesInvalidated += invalidated;
    // Cost: 50 base + 10 per page
    uint64_t costVal = (uint64_t)invalidateCycles + 10 * numPagesInRange;
    stats.invalidationCycles += costVal;

    DPRINTF(AccelPageTable, "invalidateRange: invalidated=%d, deferred=%d, "
            "cost=%d cycles\n", invalidated, deferred, (int)costVal);

    return invalidated;
}

bool
AcceleratorPageTable::pinPages(Addr vaddr, size_t size)
{
    Addr va = pageAlign(vaddr);
    size_t numPages = (size + pageSize - 1) / pageSize;
    Tick now = curTick();

    DPRINTF(AccelPageTable, "pinPages: vaddr=0x%lx, size=%d, numPages=%d\n",
            vaddr, size, numPages);

    // Check pin limit
    if (pinnedPages.size() + numPages > maxPinnedPerProcess) {
        DPRINTF(AccelPageTable, "pinPages: limit exceeded (%d + %d > %d)\n",
                pinnedPages.size(), numPages, maxPinnedPerProcess);
        stats.pinLimitExceeded++;
        return false;
    }

    // Pin all pages in range
    for (size_t i = 0; i < numPages; i++) {
        auto it = pageTable.find(va);
        if (it != pageTable.end() && it->second.valid) {
            if (!it->second.pinned) {
                it->second.pinned = true;
                it->second.pinCount = 1;
                it->second.pinStartTick = now;
                pinnedPages.insert(va);
                stats.pagesPinned++;
            } else {
                // Already pinned, increment refcount
                it->second.pinCount++;
            }
        } else {
            // Page not mapped, fail the entire pin operation
            // Rollback any pages we just pinned
            DPRINTF(AccelPageTable, "pinPages: page 0x%lx not mapped, "
                    "rolling back\n", va);
            Addr rollbackVa = pageAlign(vaddr);
            while (rollbackVa < va) {
                auto rb = pageTable.find(rollbackVa);
                if (rb != pageTable.end()) {
                    rb->second.pinCount--;
                    if (rb->second.pinCount == 0) {
                        rb->second.pinned = false;
                        rb->second.pinStartTick = 0;
                        pinnedPages.erase(rollbackVa);
                    }
                }
                rollbackVa += pageSize;
            }
            return false;
        }
        va += pageSize;
    }

    stats.pinCycles += pinLatency;
    return true;
}

size_t
AcceleratorPageTable::unpinPages(Addr vaddr, size_t size)
{
    Addr va = pageAlign(vaddr);
    size_t numPages = (size + pageSize - 1) / pageSize;

    DPRINTF(AccelPageTable, "unpinPages: vaddr=0x%lx, size=%d, numPages=%d\n",
            vaddr, size, numPages);

    for (size_t i = 0; i < numPages; i++) {
        auto it = pageTable.find(va);
        if (it != pageTable.end() && it->second.pinned) {
            it->second.pinCount--;
            if (it->second.pinCount == 0) {
                it->second.pinned = false;
                it->second.pinStartTick = 0;
                pinnedPages.erase(va);
                stats.pagesUnpinned++;
            }
        }
        va += pageSize;
    }

    // Process any deferred invalidations
    return processDeferredInvalidations(), 0;
}

bool
AcceleratorPageTable::validateAccess(Addr vaddr, bool isWrite)
{
    Addr paddr;
    bool writable;

    if (!lookup(vaddr, paddr, writable)) {
        DPRINTF(AccelPageTable, "validateAccess: vaddr=0x%lx DENIED "
                "(not mapped)\n", vaddr);
        return false;
    }

    if (isWrite && !writable) {
        DPRINTF(AccelPageTable, "validateAccess: vaddr=0x%lx DENIED "
                "(write to read-only)\n", vaddr);
        return false;
    }

    DPRINTF(AccelPageTable, "validateAccess: vaddr=0x%lx ALLOWED\n", vaddr);
    return true;
}

Cycles
AcceleratorPageTable::getLookupLatency(Addr vaddr)
{
    Addr pageVa = pageAlign(vaddr);
    Addr paddr;
    bool writable;

    if (iotlbLookup(pageVa, paddr, writable)) {
        return iotlbHitLatency;  // 3 cycles
    }

    // Full 4-level walk: 4 * 50 = 200 cycles
    stats.pageTableWalks++;
    uint64_t walkCostVal = (uint64_t)walkLatencyPerLevel * 4;
    stats.walkCycles += walkCostVal;
    return Cycles(walkCostVal);
}

void
AcceleratorPageTable::flushIOTLB()
{
    DPRINTF(AccelPageTable, "flushIOTLB: flushing all %d entries\n",
            iotlbEntries);

    for (auto &entry : iotlb) {
        entry.valid = false;
    }
}

void
AcceleratorPageTable::flushIOTLBEntry(Addr vaddr)
{
    Addr pageVa = pageAlign(vaddr);

    for (auto &entry : iotlb) {
        if (entry.valid && entry.vaddr == pageVa) {
            DPRINTF(AccelPageTable, "flushIOTLBEntry: flush 0x%lx\n", pageVa);
            entry.valid = false;
            return;
        }
    }
}

void
AcceleratorPageTable::processDeferredInvalidations()
{
    auto it = deferredInvalidations.begin();
    while (it != deferredInvalidations.end()) {
        bool canInvalidate = true;

        // Check if any pages in range are still pinned
        for (Addr va = it->startVa; va < it->endVa; va += pageSize) {
            auto pte = pageTable.find(va);
            if (pte != pageTable.end() && pte->second.pinned) {
                canInvalidate = false;
                break;
            }
        }

        if (canInvalidate) {
            DPRINTF(AccelPageTable, "processDeferredInvalidations: "
                    "processing 0x%lx - 0x%lx\n", it->startVa, it->endVa);

            for (Addr va = it->startVa; va < it->endVa; va += pageSize) {
                auto pte = pageTable.find(va);
                if (pte != pageTable.end()) {
                    pte->second.valid = false;
                    flushIOTLBEntry(va);
                }
            }
            it = deferredInvalidations.erase(it);
        } else {
            ++it;
        }
    }
}

void
AcceleratorPageTable::checkPinTimeouts()
{
    Tick now = curTick();

    for (auto va : pinnedPages) {
        auto it = pageTable.find(va);
        if (it != pageTable.end() && it->second.pinned) {
            Tick pinDuration = now - it->second.pinStartTick;
            if (pinDuration > maxPinDuration) {
                DPRINTF(AccelPageTable, "checkPinTimeouts: page 0x%lx "
                        "exceeded timeout (%llu > %llu), force unpin\n",
                        va, pinDuration, maxPinDuration);
                stats.pinTimeouts++;
                it->second.pinned = false;
                it->second.pinCount = 0;
                it->second.pinStartTick = 0;
            }
        }
    }

    // Clean up pinnedPages set
    for (auto it = pinnedPages.begin(); it != pinnedPages.end(); ) {
        auto pte = pageTable.find(*it);
        if (pte == pageTable.end() || !pte->second.pinned) {
            it = pinnedPages.erase(it);
        } else {
            ++it;
        }
    }

    // Process any deferred invalidations that may now be possible
    processDeferredInvalidations();
}

void
AcceleratorPageTable::addDeferredInvalidation(Addr startVa, Addr endVa)
{
    deferredInvalidations.emplace_back(startVa, endVa, curTick());
}

bool
AcceleratorPageTable::iotlbLookup(Addr vaddr, Addr &paddr, bool &writable)
{
    for (auto &entry : iotlb) {
        if (entry.valid && entry.vaddr == vaddr) {
            paddr = entry.paddr;
            writable = entry.writable;
            entry.lruCounter = ++lruCounter;
            return true;
        }
    }
    return false;
}

void
AcceleratorPageTable::iotlbInsert(Addr vaddr, Addr paddr, bool writable)
{
    // Find LRU entry or invalid entry
    size_t victimIdx = 0;
    uint64_t minLru = UINT64_MAX;

    for (size_t i = 0; i < iotlb.size(); i++) {
        if (!iotlb[i].valid) {
            victimIdx = i;
            break;
        }
        if (iotlb[i].lruCounter < minLru) {
            minLru = iotlb[i].lruCounter;
            victimIdx = i;
        }
    }

    DPRINTF(AccelPageTable, "iotlbInsert: vaddr=0x%lx -> idx=%d\n",
            vaddr, victimIdx);

    iotlb[victimIdx].vaddr = vaddr;
    iotlb[victimIdx].paddr = paddr;
    iotlb[victimIdx].writable = writable;
    iotlb[victimIdx].valid = true;
    iotlb[victimIdx].lruCounter = ++lruCounter;
}

bool
AcceleratorPageTable::pageTableWalk(Addr vaddr, Addr &paddr, bool &writable)
{
    auto it = pageTable.find(vaddr);
    if (it != pageTable.end() && it->second.valid) {
        paddr = it->second.paddr;
        writable = it->second.writable;
        return true;
    }
    return false;
}

// Statistics
AcceleratorPageTable::AccelPTStats::AccelPTStats(AcceleratorPageTable *parent)
    : statistics::Group(parent),
      ADD_STAT(iotlbHits, statistics::units::Count::get(),
               "Number of IOTLB hits"),
      ADD_STAT(iotlbMisses, statistics::units::Count::get(),
               "Number of IOTLB misses"),
      ADD_STAT(pageTableWalks, statistics::units::Count::get(),
               "Number of page table walks"),
      ADD_STAT(walkCycles, statistics::units::Cycle::get(),
               "Total cycles spent in page table walks"),
      ADD_STAT(batchInvalidations, statistics::units::Count::get(),
               "Number of batch invalidation requests"),
      ADD_STAT(pagesInvalidated, statistics::units::Count::get(),
               "Total pages invalidated"),
      ADD_STAT(invalidationCycles, statistics::units::Cycle::get(),
               "Total cycles spent in invalidations"),
      ADD_STAT(pagesPinned, statistics::units::Count::get(),
               "Total pages pinned"),
      ADD_STAT(pagesUnpinned, statistics::units::Count::get(),
               "Total pages unpinned"),
      ADD_STAT(pinCycles, statistics::units::Cycle::get(),
               "Total cycles spent in pin operations"),
      ADD_STAT(deferredInvalidations, statistics::units::Count::get(),
               "Number of deferred invalidations (pinned pages)"),
      ADD_STAT(pinTimeouts, statistics::units::Count::get(),
               "Number of pin timeouts"),
      ADD_STAT(pinLimitExceeded, statistics::units::Count::get(),
               "Number of pin requests denied due to limit")
{
}

} // namespace gem5
