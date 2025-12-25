#ifndef __HWACC_ACCELERATOR_CONTEXT_HH__
#define __HWACC_ACCELERATOR_CONTEXT_HH__

#include <map>
#include <memory>
#include <vector>

#include "base/statistics.hh"
#include "base/types.hh"
#include "hwacc/accelerator_page_table.hh"
#include "params/AcceleratorContextManager.hh"
#include "sim/clocked_object.hh"

namespace gem5
{

/**
 * Per-process context for accelerator isolation
 */
struct AcceleratorContext
{
    uint64_t pid;                 // Process ID
    Tick lastAccessTick;          // For lazy context switch
    bool valid;                   // Context is active

    // Per-context page table instance
    std::unique_ptr<std::map<Addr, AcceleratorPTE>> mappings;

    AcceleratorContext()
        : pid(0), lastAccessTick(0), valid(false),
          mappings(std::make_unique<std::map<Addr, AcceleratorPTE>>()) {}

    AcceleratorContext(uint64_t p)
        : pid(p), lastAccessTick(0), valid(true),
          mappings(std::make_unique<std::map<Addr, AcceleratorPTE>>()) {}
};

/**
 * AcceleratorContextManager - Manages per-process isolation for shared
 * accelerator with lazy context switching.
 *
 * Features:
 * - Per-process page table contexts
 * - Lazy context switch (only flush IOTLB on pid change)
 * - Centralized mmu_notifier callback handling
 * - Process registration/deregistration
 */
class AcceleratorContextManager : public ClockedObject
{
  public:
    PARAMS(AcceleratorContextManager);
    AcceleratorContextManager(const Params &p);
    ~AcceleratorContextManager();

    /**
     * Set the associated page table (called during initialization)
     */
    void setPageTable(AcceleratorPageTable *pt) { pageTable = pt; }

    /**
     * Register a new process context
     * @param pid Process ID
     */
    void registerProcess(uint64_t pid);

    /**
     * Deregister a process (cleanup on exit)
     * @param pid Process ID
     */
    void deregisterProcess(uint64_t pid);

    /**
     * Switch to a different process context (lazy)
     * @param pid Target process ID
     * @return Cycles incurred for context switch (0 if same pid)
     */
    Cycles switchContext(uint64_t pid);

    /**
     * Get current active process ID
     */
    uint64_t getCurrentPid() const { return currentPid; }

    /**
     * Map pages in a specific process context
     */
    void mapForProcess(uint64_t pid, Addr vaddr, Addr paddr,
                       size_t size, bool writable);

    /**
     * Unmap pages in a specific process context
     */
    void unmapForProcess(uint64_t pid, Addr vaddr, size_t size);

    /**
     * Validate access for current process context
     * @param vaddr Virtual address
     * @param isWrite true if write access
     * @return true if access is valid
     */
    bool validateAccess(Addr vaddr, bool isWrite);

    /**
     * mmu_notifier callback - invalidate range for all contexts or
     * specific pid
     * @param pid Process ID (0 for all processes)
     * @param startVa Start virtual address
     * @param endVa End virtual address
     */
    void mmuNotifierInvalidate(uint64_t pid, Addr startVa, Addr endVa);

    /**
     * Check if process is registered
     */
    bool isProcessRegistered(uint64_t pid) const {
        return contexts.find(pid) != contexts.end();
    }

    /**
     * Get number of registered processes
     */
    size_t getNumProcesses() const { return contexts.size(); }

    // Statistics
    struct ContextStats : public statistics::Group
    {
        ContextStats(AcceleratorContextManager *parent);

        statistics::Scalar contextSwitches;
        statistics::Scalar contextSwitchCycles;
        statistics::Scalar lazySwitchesAvoided;
        statistics::Scalar processesRegistered;
        statistics::Scalar processesDeregistered;
        statistics::Scalar mmuNotifierCalls;
        statistics::Scalar accessValidations;
        statistics::Scalar accessDenied;
    } stats;

  private:
    // Configuration
    const Cycles contextSwitchLatency;  // 1500 cycles for lazy switch

    // Associated page table
    AcceleratorPageTable *pageTable;

    // Per-process contexts
    std::map<uint64_t, AcceleratorContext> contexts;

    // Current active process
    uint64_t currentPid;

    /**
     * Load context for process into page table
     */
    void loadContext(uint64_t pid);

    /**
     * Save current context from page table
     */
    void saveContext();
};

} // namespace gem5

#endif // __HWACC_ACCELERATOR_CONTEXT_HH__
