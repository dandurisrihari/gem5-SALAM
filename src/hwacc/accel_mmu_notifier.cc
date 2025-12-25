#include "hwacc/accel_mmu_notifier.hh"

#include "base/trace.hh"
#include "debug/AccelMmuNotifier.hh"
#include "hwacc/accelerator_context.hh"

namespace gem5
{

void
AccelMmuNotifier::registerContext(AcceleratorContextManager *ctx)
{
    if (ctx) {
        DPRINTF(AccelMmuNotifier, "Registering accelerator context manager\n");
        contexts.push_back(ctx);
    }
}

void
AccelMmuNotifier::unregisterContext(AcceleratorContextManager *ctx)
{
    if (ctx) {
        DPRINTF(AccelMmuNotifier,
                "Unregistering accelerator context manager\n");
        contexts.remove(ctx);
    }
}

void
AccelMmuNotifier::notifyInvalidateRange(uint64_t pid, Addr startVa, Addr endVa)
{
    DPRINTF(AccelMmuNotifier, "notifyInvalidateRange: pid=%llu, "
            "range=0x%lx-0x%lx, num_contexts=%d\n",
            pid, startVa, endVa, contexts.size());

    for (auto *ctx : contexts) {
        ctx->mmuNotifierInvalidate(pid, startVa, endVa);
    }
}

void
notifyAcceleratorInvalidate(uint64_t pid, Addr startVa, Addr endVa)
{
    AccelMmuNotifier &notifier = AccelMmuNotifier::getInstance();
    if (notifier.hasRegisteredContexts()) {
        notifier.notifyInvalidateRange(pid, startVa, endVa);
    }
}

} // namespace gem5
