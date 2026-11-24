import SwiftUI
import Foundation

@MainActor final class InspectionStore: ObservableObject {
    @Published var cache = Cache()
    @Published var error: String?
    @Published var busy = false
    @Published private(set) var refreshing = false
    private let refreshCoordinator = RefreshCoordinator()
    private var locallyDeletedInspections: Set<String> = []
    private var locallyDeletedMedia: Set<String> = []
    @Published var libraryNotice = ""
    private var suggestionSync: (id: UUID, task: Task<Void, Error>)?
    let directory: URL
    private var activeSyncs: [String: (id: UUID, task: Task<Void, Error>)] = [:]
    init() {
        directory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("JBIInspections", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: directory.path)
            let file = directory.appendingPathComponent("cache.json")
            if FileManager.default.fileExists(atPath: file.path) {
                cache = try JSONDecoder().decode(Cache.self, from: Data(contentsOf: file))
            }
        } catch { self.error = "Local storage: \(error.localizedDescription)" }
        locallyDeletedInspections.formUnion(cache.pendingInspectionDeletions ?? [])
        locallyDeletedMedia.formUnion(cache.pendingMediaDeletions ?? [])
    }
    var api: API { API(baseURL: UserDefaults.standard.string(forKey: "backendURL") ?? API.defaultBaseURL, token: SecureToken.read()) }
    var companyNames: [String] { (cache.savedRows ?? []).filter { $0.kind == "company" }.map(\.company) }
    func saveCompanyNames(_ value: String) {
        for name in Set(value.components(separatedBy: CharacterSet(charactersIn: ";\n")).map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }) {
            saveSuggestion(SavedRow(kind: "company", company: name))
        }
    }
    func saveSuggestion(_ row: SavedRow) {
        guard !(row.kind == "company" ? [row.company] : row.kind == "attendee" ? [row.name,row.company,row.title] : [row.location,row.action]).allSatisfy({ $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) else { return }
        var rows = cache.savedRows ?? []
        if rows.contains(where: { $0.summary.caseInsensitiveCompare(row.summary) == .orderedSame && $0.kind == row.kind }) { libraryNotice = "This row is already saved."; return }
        rows.insert(row, at: 0); cache.savedRows = rows
        if cache.pendingSavedRows == nil { cache.pendingSavedRows = [] }
        cache.pendingSavedRows?.insert(row.id); persist()
        libraryNotice = "Row saved on this phone."
        Task {
            do { try await syncSuggestions(); if connected { libraryNotice = "Row saved and synced for reuse on web and iPhone." } }
            catch { libraryNotice = "Saved on this phone · sync pending"; self.error = "Saved on this phone; library sync pending: " + error.localizedDescription }
        }
    }
    func syncSuggestions() async throws {
        guard connected else { return }
        while let previous = suggestionSync {
            let result = await previous.task.result
            if suggestionSync?.id == previous.id { suggestionSync = nil }
            try result.get()
        }
        let id = UUID()
        let task = Task { try await performSuggestionSync() }
        suggestionSync = (id, task)
        defer { if suggestionSync?.id == id { suggestionSync = nil } }
        try await task.value
    }
    private func performSuggestionSync() async throws {
        for id in cache.pendingSavedRows ?? [] {
            guard let row = cache.savedRows?.first(where: { $0.id == id }) else { continue }
            let data = try await api.request("/saved-rows", method: "POST", body: JSONEncoder().encode(row))
            let remote = try JSONDecoder().decode(SavedRow.self, from: data)
            cache.savedRows?.removeAll { $0.id == id || $0.id == remote.id }
            cache.savedRows?.insert(remote, at: 0); cache.pendingSavedRows?.remove(id); persist()
        }
        let remote = try JSONDecoder().decode([SavedRow].self, from: await api.request("/saved-rows"))
        let pending = (cache.savedRows ?? []).filter { cache.pendingSavedRows?.contains($0.id) == true }
        cache.savedRows = pending + remote.filter { row in !pending.contains(where: { $0.id == row.id }) }; persist()
    }
    func deleteSuggestion(_ row: SavedRow) async throws {
        if connected { try await syncSuggestions(); _ = try await api.request("/saved-rows/\(row.id)", method: "DELETE") }
        else if cache.pendingSavedRows?.contains(row.id) != true { throw APIError(message: "Connect before deleting a synced library row.") }
        cache.savedRows?.removeAll { $0.id == row.id }; cache.pendingSavedRows?.remove(row.id); persist()
    }
    func persist() {
        do { try JSONEncoder().encode(cache).write(to: directory.appendingPathComponent("cache.json"), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication]) }
        catch { self.error = "Could not save inspection: \(error.localizedDescription)" }
    }
    func save(_ inspection: Inspection) {
        if let i = cache.inspections.firstIndex(where: { $0.id == inspection.id }) { cache.inspections[i] = inspection }
        else { cache.inspections.insert(inspection, at: 0) }
        cache.dirty.insert(inspection.id); persist()
    }
    @discardableResult
    func addMedia(_ data: Data, to inspection: Inspection, kind: String, mime: String, ext: String) throws -> String {
        guard cache.inspections.contains(where: { $0.id == inspection.id }) else { throw APIError(message: "This inspection was deleted; evidence import stopped.") }
        var item = LocalMedia(inspectionID: inspection.id, kind: kind, relativePath: "", mime: mime)
        item.relativePath = item.id + "." + ext
        try data.write(to: directory.appendingPathComponent(item.relativePath), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        cache.media.append(item); cache.dirty.insert(inspection.id); persist()
        return item.id
    }
    func mediaURL(_ item: LocalMedia) -> URL { directory.appendingPathComponent(item.relativePath) }
    var connected: Bool { !SecureToken.read().isEmpty }
    func flushDeletions() async throws {
        for id in cache.pendingInspectionDeletions ?? [] {
            _ = try await api.request("/inspections/\(id)", method: "DELETE")
            cache.pendingInspectionDeletions?.remove(id); persist()
        }
        for id in cache.pendingMediaDeletions ?? [] {
            _ = try await api.request("/media/\(id)", method: "DELETE")
            cache.pendingMediaDeletions?.remove(id); persist()
        }
    }
    func removeInspection(_ id: String) {
        locallyDeletedInspections.insert(id)
        activeSyncs[id]?.task.cancel()
        for (artifact,owner) in cache.artifactOwners ?? [:] where owner == id {
            try? FileManager.default.removeItem(at: directory.appendingPathComponent("exports").appendingPathComponent(artifact))
            cache.artifactOwners?.removeValue(forKey: artifact)
        }
        for item in cache.media.filter({ $0.inspectionID == id }) { try? FileManager.default.removeItem(at: mediaURL(item)) }
        cache.media.removeAll { $0.inspectionID == id }; cache.inspections.removeAll { $0.id == id }; cache.dirty.remove(id)
        if cache.pendingInspectionDeletions == nil { cache.pendingInspectionDeletions = [] }
        cache.pendingInspectionDeletions?.insert(id); persist()
    }
    func removeMedia(_ id: String) {
        guard let item = cache.media.first(where: { $0.id == id }) else { return }
        locallyDeletedMedia.insert(id)
        try? FileManager.default.removeItem(at: mediaURL(item)); cache.media.removeAll { $0.id == id }
        for i in cache.inspections.indices {
            for j in cache.inspections[i].reports.indices { cache.inspections[i].reports[j].photo_references.removeAll { $0 == id } }
        }
        if cache.pendingMediaDeletions == nil { cache.pendingMediaDeletions = [] }
        cache.pendingMediaDeletions?.insert(id); cache.dirty.insert(item.inspectionID); persist()
    }
    func sync(_ inspection: Inspection) async throws {
        while let prior = activeSyncs[inspection.id] {
            let finished = await prior.task.result
            if activeSyncs[inspection.id]?.id == prior.id { activeSyncs.removeValue(forKey: inspection.id) }
            try finished.get()
        }
        guard let latest = cache.inspections.first(where: { $0.id == inspection.id }) else { return }
        let token = UUID()
        let task = Task { try await performSync(latest) }
        activeSyncs[inspection.id] = (token, task)
        defer { if activeSyncs[inspection.id]?.id == token { activeSyncs.removeValue(forKey: inspection.id) } }
        try await task.value
    }
    private func performSync(_ inspection: Inspection) async throws {
        try await flushDeletions()
        guard cache.inspections.contains(where: { $0.id == inspection.id }) else { return }
        var outbound = inspection
        outbound.prepareAttendees()
        _ = try await api.request("/inspections/\(inspection.id)", method: "PUT", body: JSONEncoder().encode(outbound))
        let snapshot = cache.media.filter { $0.inspectionID == inspection.id }
        let records = try JSONSerialization.jsonObject(with: await api.request("/inspections/\(inspection.id)/media")) as? [[String: Any]] ?? []
        let remoteIDs = Set(records.compactMap { $0["id"] as? String })
        let deleted = try JSONDecoder().decode(DeletionState.self, from: await api.request("/sync/deletions"))
        for item in snapshot where !deleted.media.contains(item.id) {
            if !item.uploaded || !remoteIDs.contains(item.id) {
                _ = try await api.request("/inspections/\(inspection.id)/media?kind=\(item.kind)&filename=\(item.relativePath)",
                    method: "POST", body: Data(contentsOf: mediaURL(item)), mime: item.mime, headers: ["X-Asset-ID": item.id])
            }
            _ = try await api.json("/media/\(item.id)", method: "PUT", object: ["note": item.note, "equipment": item.equipment])
            if let index = cache.media.firstIndex(where: { $0.id == item.id }) { cache.media[index].uploaded = true }
        }
        if cache.inspections.first(where: { $0.id == inspection.id }) == inspection {
            let current = cache.media.filter { $0.inspectionID == inspection.id }
            if current.map({ $0.id + $0.note + $0.equipment }) == snapshot.map({ $0.id + $0.note + $0.equipment }) { cache.dirty.remove(inspection.id) }
        }
        persist()
    }
    func syncAll() async throws {
        try await refreshCoordinator.run {
            self.refreshing = true
            defer { self.refreshing = false }
            try await self.performSyncAll()
        }
    }
    private func performSyncAll() async throws {
        try await refresh()
        for inspection in cache.inspections where cache.dirty.contains(inspection.id) { try await sync(inspection) }
        try await refresh()
    }
    private func canApplyRefresh(_ id: String) -> Bool {
        RefreshMergePolicy.allowsInspection(id, cache: cache, deleted: locallyDeletedInspections)
    }
    func refresh() async throws {
        try await syncSuggestions()
        try await flushDeletions()
        let deleted = try JSONDecoder().decode(DeletionState.self, from: await api.request("/sync/deletions"))
        locallyDeletedInspections.formUnion(deleted.inspections); locallyDeletedMedia.formUnion(deleted.media)
        for item in cache.media where deleted.media.contains(item.id) || deleted.inspections.contains(item.inspectionID) { try? FileManager.default.removeItem(at: mediaURL(item)) }
        cache.media.removeAll { deleted.media.contains($0.id) || deleted.inspections.contains($0.inspectionID) }
        cache.inspections.removeAll { deleted.inspections.contains($0.id) }; cache.dirty.subtract(deleted.inspections)
        let remote = try JSONDecoder().decode([Inspection].self, from: await api.request("/inspections"))
        let remoteIDs = Set(remote.map(\.id))
        for local in cache.inspections where !remoteIDs.contains(local.id) && !deleted.inspections.contains(local.id) { cache.dirty.insert(local.id) }
        for inspection in remote where !cache.dirty.contains(inspection.id) && !locallyDeletedInspections.contains(inspection.id) && cache.pendingInspectionDeletions?.contains(inspection.id) != true {
            if let i = cache.inspections.firstIndex(where: { $0.id == inspection.id }) { cache.inspections[i] = inspection }
            else { cache.inspections.append(inspection) }
            let baseline = cache.media.filter { $0.inspectionID == inspection.id }.reduce(into: [String:LocalMedia]()) { $0[$1.id] = $1 }
            let records = try JSONSerialization.jsonObject(with: await api.request("/inspections/\(inspection.id)/media")) as? [[String: Any]] ?? []
            for record in records {
                guard canApplyRefresh(inspection.id), let id = record["id"] as? String, let kind = record["kind"] as? String, let mime = record["mime"] as? String else { continue }
                let current = cache.media.first { $0.id == id }
                guard RefreshMergePolicy.allowsMedia(id, before: baseline[id], current: current, pending: cache.pendingMediaDeletions ?? [], deleted: locallyDeletedMedia) else { continue }
                let ext = ["image/png": "png", "image/jpeg": "jpg", "audio/wav": "wav", "audio/mpeg": "mp3", "audio/mp4": "m4a", "video/mp4": "mp4", "video/quicktime": "mov"][mime] ?? "bin"
                if let current {
                    if !FileManager.default.fileExists(atPath: mediaURL(current).path) {
                        let bytes = try await api.request("/media/\(id)")
                        guard canApplyRefresh(inspection.id), RefreshMergePolicy.allowsMedia(id, before: baseline[id], current: cache.media.first { $0.id == id }, pending: cache.pendingMediaDeletions ?? [], deleted: locallyDeletedMedia) else { continue }
                        try bytes.write(to: mediaURL(current), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
                    }
                    guard let index = cache.media.firstIndex(where: { $0.id == id }) else { continue }
                    cache.media[index].note = record["note"] as? String ?? ""; cache.media[index].equipment = record["equipment"] as? String ?? ""
                } else {
                    let data = try await api.request("/media/\(id)")
                    guard canApplyRefresh(inspection.id), RefreshMergePolicy.allowsMedia(id, before: baseline[id], current: cache.media.first { $0.id == id }, pending: cache.pendingMediaDeletions ?? [], deleted: locallyDeletedMedia) else { continue }
                    let path = id + "." + ext
                    try data.write(to: directory.appendingPathComponent(path), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
                    cache.media.append(LocalMedia(id: id, inspectionID: inspection.id, kind: kind, relativePath: path,
                        note: record["note"] as? String ?? "", equipment: record["equipment"] as? String ?? "", uploaded: true, mime: mime))
                }
            }
        }
        persist()
    }
    func download(_ artifact: Artifact, inspectionID: String? = nil) async throws -> URL {
        let data = try await api.request("/artifacts/\(artifact.id)")
        let folder = directory.appendingPathComponent("exports", isDirectory: true).appendingPathComponent(artifact.id, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let url = folder.appendingPathComponent(URL(fileURLWithPath: artifact.filename).lastPathComponent)
        try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        if let inspectionID {
            if cache.artifactOwners == nil { cache.artifactOwners = [:] }
            cache.artifactOwners?[artifact.id] = inspectionID; persist()
        }
        return url
    }
}
