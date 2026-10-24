import SwiftUI
import Foundation

@MainActor final class InspectionStore: ObservableObject {
    @Published var cache = Cache()
    @Published var error: String?
    @Published var busy = false
    let directory: URL
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
    }
    var api: API { API(baseURL: UserDefaults.standard.string(forKey: "backendURL") ?? API.defaultBaseURL, token: SecureToken.read()) }
    func persist() {
        do { try JSONEncoder().encode(cache).write(to: directory.appendingPathComponent("cache.json"), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication]) }
        catch { self.error = "Could not save inspection: \(error.localizedDescription)" }
    }
    func save(_ inspection: Inspection) {
        if let i = cache.inspections.firstIndex(where: { $0.id == inspection.id }) { cache.inspections[i] = inspection }
        else { cache.inspections.insert(inspection, at: 0) }
        cache.dirty.insert(inspection.id); persist()
    }
    func addMedia(_ data: Data, to inspection: Inspection, kind: String, mime: String, ext: String) throws {
        guard cache.inspections.contains(where: { $0.id == inspection.id }) else { throw APIError(message: "This inspection was deleted; evidence import stopped.") }
        var item = LocalMedia(inspectionID: inspection.id, kind: kind, relativePath: "", mime: mime)
        item.relativePath = item.id + "." + ext
        try data.write(to: directory.appendingPathComponent(item.relativePath), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        cache.media.append(item); cache.dirty.insert(inspection.id); persist()
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
        try? FileManager.default.removeItem(at: mediaURL(item)); cache.media.removeAll { $0.id == id }
        for i in cache.inspections.indices {
            for j in cache.inspections[i].reports.indices { cache.inspections[i].reports[j].photo_references.removeAll { $0 == id } }
        }
        if cache.pendingMediaDeletions == nil { cache.pendingMediaDeletions = [] }
        cache.pendingMediaDeletions?.insert(id); cache.dirty.insert(item.inspectionID); persist()
    }
    func sync(_ inspection: Inspection) async throws {
        try await flushDeletions()
        guard cache.inspections.contains(where: { $0.id == inspection.id }) else { return }
        _ = try await api.request("/inspections/\(inspection.id)", method: "PUT", body: JSONEncoder().encode(inspection))
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
        try await refresh()
        for inspection in cache.inspections where cache.dirty.contains(inspection.id) { try await sync(inspection) }
        try await refresh()
    }
    func refresh() async throws {
        try await flushDeletions()
        let deleted = try JSONDecoder().decode(DeletionState.self, from: await api.request("/sync/deletions"))
        for item in cache.media where deleted.media.contains(item.id) || deleted.inspections.contains(item.inspectionID) { try? FileManager.default.removeItem(at: mediaURL(item)) }
        cache.media.removeAll { deleted.media.contains($0.id) || deleted.inspections.contains($0.inspectionID) }
        cache.inspections.removeAll { deleted.inspections.contains($0.id) }; cache.dirty.subtract(deleted.inspections)
        let remote = try JSONDecoder().decode([Inspection].self, from: await api.request("/inspections"))
        let remoteIDs = Set(remote.map(\.id))
        for local in cache.inspections where !remoteIDs.contains(local.id) && !deleted.inspections.contains(local.id) { cache.dirty.insert(local.id) }
        for inspection in remote where !cache.dirty.contains(inspection.id) {
            if let i = cache.inspections.firstIndex(where: { $0.id == inspection.id }) { cache.inspections[i] = inspection }
            else { cache.inspections.append(inspection) }
            let records = try JSONSerialization.jsonObject(with: await api.request("/inspections/\(inspection.id)/media")) as? [[String: Any]] ?? []
            for record in records {
                guard let id = record["id"] as? String, let kind = record["kind"] as? String, let mime = record["mime"] as? String else { continue }
                let ext = mime == "image/png" ? "png" : mime == "image/jpeg" ? "jpg" : mime == "audio/wav" ? "wav" : mime == "audio/mpeg" ? "mp3" : "m4a"
                if let index = cache.media.firstIndex(where: { $0.id == id }) {
                    if !FileManager.default.fileExists(atPath: mediaURL(cache.media[index]).path) {
                        let bytes = try await api.request("/media/\(id)")
                        try bytes.write(to: mediaURL(cache.media[index]), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
                    }
                    cache.media[index].note = record["note"] as? String ?? ""; cache.media[index].equipment = record["equipment"] as? String ?? ""
                } else {
                    let data = try await api.request("/media/\(id)")
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
