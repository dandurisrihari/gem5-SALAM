#ifndef __HWACC_ACCELERATOR_PAGE_TABLE_HH__
#define __HWACC_ACCELERATOR_PAGE_TABLE_HH__

#include <cstdint>
#include <list>
#include <map>
#include <set>
#include <vector>

#include "base/statistics.hh"
#include "base/types.hh"
#include "params/AcceleratorPageTable.hh"
#include "sim/clocked_object.hh"
#include "sim/sim_object.hh"

namespace gem5
{

/**
 * Page Table Entry for accelerator page table
 * Models ARM 4KB page with permissions
 */
struct AcceleratorPTE
{
    Addr paddr;          // Physical address
    bool valid;          // Entry is valid
    bool writable;       // Write permission
    bool pinned;         // Page is pinned (in-use by DMA)
    uint32_t pinCount;   // Reference count for nested pins
    Tick pinStartTick;   // When page was pinned (for timeout)

    AcceleratorPTE()
        : paddr(0), valid(false), writable(false),
          pinned(false), pinCount(0), pinStartTick(0) {}

    AcceleratorPTE(Addr pa, bool w)
        : paddr(pa), valid(true), writable(w),
          pinned(false), pinCount(0), pinStartTick(0) {}
};

/**
 * IOTLB Entry for caching recent translations
 */
struct IOTLBEntry
{
    Addr vaddr;          // Virtual address (page aligned)
    Addr paddr;          // Physical address
    bool valid;          // Entry is valid
    bool writable;       // Write permission
    uint64_t lruCounter; // For LRU replacement

    IOTLBEntry()
        : vaddr(0), paddr(0), valid(false), writable(false), lruCounter(0) {}
};

/**
 * Deferred invalidation request (for pinned pages)
 */
struct DeferredInvalidation
{
    Addr startVa;
    Addr endVa;
    Tick requestTick;

    DeferredInvalidation(Addr start, Addr end, Tick tick)
        : startVa(start), endVa(end), requestTick(tick) {}
};

/**
 * AcceleratorPageTable - 4-level ARM-style page table for accelerator
 * with IOTLB caching and page pinning support for edge AI security.
 *
 * Features:
 * - 4-level page table walk (L0-L3) for 4KB pages
 * - 64-entry IOTLB with LRU replacement
 * - Page pinning for DMA operations (get_user_pages semantics)
 * - Batch invalidation support (mmu_notifier style)
 * - Deferred invalidation for pinned pages
 */
class AcceleratorPageTable : public ClockedObject
{
  public:
    PARAMS(AcceleratorPageTable);
    AcceleratorPageTable(const Params &p);
    ~AcceleratorPageTable();

    // Page table operations
    void map(Addr vaddr, Addr paddr, size_t size, bool writable);
    void unmap(Addr vaddr, size_t size);

    /**
     * Lookup address translation
     * @param vaddr Virtual address to translate
     * @param paddr Output physical address
     * @param writable Output write permission
     * @return true if translation found and valid
     */
    bool lookup(Addr vaddr, Addr &paddr, bool &writable);

    /**
     * Batch invalidate a range of addresses (mmu_notifier style)
     * @param startVa Start of virtual address range
     * @param endVa End of virtual address range
     * @return Number of pages actually invalidated (pinned pages deferred)
     */
    size_t invalidateRange(Addr startVa, Addr endVa);

    /**
     * Pin pages for DMA operation (models get_user_pages)
     * @param vaddr Start virtual address
     * @param size Size in bytes
     * @return true if pages successfully pinned, false if limit exceeded
     */
    bool pinPages(Addr vaddr, size_t size);

    /**
     * Unpin pages after DMA completion
     * @param vaddr Start virtual address
     * @param size Size in bytes
     * @return Number of deferred invalidations processed
     */
    size_t unpinPages(Addr vaddr, size_t size);

    /**
     * Check if address is valid for given permissions
     * @param vaddr Virtual address
     * @param isWrite true if write access
     * @return true if access is allowed
     */
    bool validateAccess(Addr vaddr, bool isWrite);

    /**
     * Get the latency for a lookup (IOTLB hit vs page walk)
     */
    Cycles getLookupLatency(Addr vaddr);

    /**
     * Flush entire IOTLB
     */
    void flushIOTLB();

    /**
     * Flush specific IOTLB entry
     */
    void flushIOTLBEntry(Addr vaddr);

    /**
     * Process any deferred invalidations for unpinned pages
     */
    void processDeferredInvalidations();

    /**
     * Check for pin timeouts and force unpin if exceeded
     */
    void checkPinTimeouts();

    /**
     * Get number of currently pinned pages
     */
    size_t getPinnedPageCount() const { return pinnedPages.size(); }

    /**
     * Add a deferred invalidation (for invalidating pinned page)
     */
    void addDeferredInvalidation(Addr startVa, Addr endVa);

    // Statistics
    struct AccelPTStats : public statistics::Group
    {
        AccelPTStats(AcceleratorPageTable *parent);

        statistics::Scalar iotlbHits;
        statistics::Scalar iotlbMisses;
        statistics::Scalar pageTableWalks;
        statistics::Scalar walkCycles;
        statistics::Scalar batchInvalidations;
        statistics::Scalar pagesInvalidated;
        statistics::Scalar invalidationCycles;
        statistics::Scalar pagesPinned;
        statistics::Scalar pagesUnpinned;
        statistics::Scalar pinCycles;
        statistics::Scalar deferredInvalidations;
        statistics::Scalar pinTimeouts;
        statistics::Scalar pinLimitExceeded;
    } stats;

  private:
    // Configuration
    const size_t pageSize;           // 4KB
    const size_t iotlbEntries;       // 64 entries
    const Cycles iotlbHitLatency;    // 3 cycles
    const Cycles walkLatencyPerLevel;// 50 cycles per level
    const Cycles invalidateCycles;   // 50 base + 10 per page
    const Cycles pinLatency;         // 50 cycles
    const Tick maxPinDuration;       // 10ms timeout
    const size_t maxPinnedPerProcess;// 256 pages (1MB)

    // Page table storage (simplified: direct vaddr -> PTE map)
    // In real impl would be 4-level tree, but functionally equivalent
    std::map<Addr, AcceleratorPTE> pageTable;

    // IOTLB cache
    std::vector<IOTLBEntry> iotlb;
    uint64_t lruCounter;

    // Pinned page tracking
    std::set<Addr> pinnedPages;

    // Deferred invalidations (for pinned pages)
    std::list<DeferredInvalidation> deferredInvalidations;

    // Helper functions
    Addr pageAlign(Addr addr) const { return addr & ~(pageSize - 1); }
    size_t pageOffset(Addr addr) const { return addr & (pageSize - 1); }

    /**
     * IOTLB lookup
     * @return true if hit, updates paddr and writable
     */
    bool iotlbLookup(Addr vaddr, Addr &paddr, bool &writable);

    /**
     * Insert entry into IOTLB (LRU replacement)
     */
    void iotlbInsert(Addr vaddr, Addr paddr, bool writable);

    /**
     * Perform 4-level page table walk
     * @return true if translation found
     */
    bool pageTableWalk(Addr vaddr, Addr &paddr, bool &writable);
};

} // namespace gem5

#endif // __HWACC_ACCELERATOR_PAGE_TABLE_HH__
