import Foundation

@MainActor final class Signal {
    private var signalled = false
    private var waiters: [CheckedContinuation<Void,Never>] = []
    func wait() async {
        if signalled { return }
        await withCheckedContinuation { waiters.append($0) }
    }
    func signal() {
        signalled = true
        let pending = waiters; waiters = []
        for waiter in pending { waiter.resume() }
    }
}

@main struct SyncRegression {
    @MainActor static func main() async throws {
        precondition(SyncFailure.refreshMessage(CancellationError(), callerCancelled: false) == nil)
        precondition(SyncFailure.refreshMessage(URLError(.cancelled), callerCancelled: false) == nil)
        precondition(SyncFailure.refreshMessage(NSError(domain: NSURLErrorDomain, code: -999), callerCancelled: false) == nil)
        for error in [URLError(.timedOut), URLError(.notConnectedToInternet), URLError(.cannotConnectToHost)] {
            precondition(SyncFailure.refreshMessage(error, callerCancelled: false) != nil)
        }
        let server = NSError(domain: "Backend", code: 503, userInfo: [NSLocalizedDescriptionKey:"Server unavailable"])
        precondition(SyncFailure.refreshMessage(server, callerCancelled: false)?.contains("Server unavailable") == true)
        precondition(SyncFailure.refreshMessage(server, callerCancelled: true) == nil)
        precondition(!SyncFailure.isCancellation(NSError(domain:"Backend", code:-999, userInfo:[NSLocalizedDescriptionKey:"Cancelled by server policy"])))

        let coordinator = RefreshCoordinator()
        let started = Signal(), release = Signal(), joined = Signal()
        var runs = 0, finished = false
        let initialView = Task {
            try await coordinator.run {
                runs += 1; started.signal()
                await release.wait()
                try Task.checkCancellation()
                finished = true
            }
        }
        await started.wait()
        let manualRefresh = Task {
            joined.signal()
            try await coordinator.run { runs += 100 }
        }
        await joined.wait()
        initialView.cancel() // Simulate SwiftUI cancelling the list's .task.
        release.signal()
        try await initialView.value; try await manualRefresh.value
        precondition(runs == 1 && finished, "Navigation must not cancel the shared refresh or start a duplicate")
        try await coordinator.run { runs += 1 }
        precondition(runs == 2, "A later refresh must be able to start")
        do {
            try await coordinator.run { throw URLError(.timedOut) }
            preconditionFailure("Real network failures must be propagated")
        } catch { precondition(!SyncFailure.isCancellation(error)) }
        try await coordinator.run { runs += 1 }
        precondition(runs == 3, "Failure cleanup must allow a retry")
        print("Refresh cancellation filtering, shared sync ownership, concurrent joining, real failures and retry regression checks passed.")
    }
}
