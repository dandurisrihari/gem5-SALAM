#ifndef __HWACC_ACCEL_MMU_NOTIFIER_HH__
#define __HWACC_ACCEL_MMU_NOTIFIER_HH__

#include <list>

#include "base/types.hh"

namespace gem5
{

class AcceleratorContextManager;

/**
 * AccelMmuNotifier - Global registry for accelerator MMU notification
 *
 * This provides a way for accelerator page tables to receive notifications
 * when the CPU page tables are modified (similar to Linux mmu_notifier).
 *
 * Usage:
 * 1. AcceleratorContextManager registers itself on construction
 * 2. When CPU unmaps memory, call notifyInvalidateRange()
 * 3. All registered accelerator contexts will invalidate that range
 *
 * This is a singleton pattern for simplicity.
 */
class AccelMmuNotifier
{
  public:
    static AccelMmuNotifier& getInstance()
    {
        static AccelMmuNotifier instance;
        return instance;
    }

    /**
     * Register an accelerator context manager to receive notifications
     */
    void registerContext(AcceleratorContextManager *ctx);

    /**
     * Unregister an accelerator context manager
     */
    void unregisterContext(AcceleratorContextManager *ctx);

    /**
     * Notify all registered accelerators of an address range invalidation
     * @param pid Process ID (0 for all processes)
     * @param startVa Start virtual address
     * @param endVa End virtual address
     */
    void notifyInvalidateRange(uint64_t pid, Addr startVa, Addr endVa);

    /**
     * Check if any contexts are registered
     */
    bool hasRegisteredContexts() const { return !contexts.empty(); }

  private:
    AccelMmuNotifier() = default;
    ~AccelMmuNotifier() = default;
    AccelMmuNotifier(const AccelMmuNotifier&) = delete;
    AccelMmuNotifier& operator=(const AccelMmuNotifier&) = delete;

    std::list<AcceleratorContextManager*> contexts;
};

/**
 * Helper function to be called from mem_state.cc after TLB flush
 * This checks if any accelerators are registered and notifies them
 */
void notifyAcceleratorInvalidate(uint64_t pid, Addr startVa, Addr endVa);

} // namespace gem5

#endif // __HWACC_ACCEL_MMU_NOTIFIER_HH__
