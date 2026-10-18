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
    var api: API { API(baseURL: UserDefaults.standard.string(forKey: "backendURL") ?? "", token: SecureToken.read()) }
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
        var item = LocalMedia(inspectionID: inspection.id, kind: kind, relativePath: "", mime: mime)
        item.relativePath = item.id + "." + ext
        try data.write(to: directory.appendingPathComponent(item.relativePath), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        cache.media.append(item); cache.dirty.insert(inspection.id); persist()
    }
    func mediaURL(_ item: LocalMedia) -> URL { directory.appendingPathComponent(item.relativePath) }
    func sync(_ inspection: Inspection) async throws {
        // PUT with a client UUID is idempotent, including the first offline-created inspection.
        _ = try await api.request("/inspections/\(inspection.id)", method: "PUT", body: JSONEncoder().encode(inspection))
        for item in cache.media.filter({ $0.inspectionID == inspection.id }) {
            if !item.uploaded {
                _ = try await api.request("/inspections/\(inspection.id)/media?kind=\(item.kind)&filename=\(item.relativePath)",
                    method: "POST", body: Data(contentsOf: mediaURL(item)), mime: item.mime, headers: ["X-Asset-ID": item.id])
            }
            _ = try await api.json("/media/\(item.id)", method: "PUT", object: ["note": item.note, "equipment": item.equipment])
            if let index = cache.media.firstIndex(where: { $0.id == item.id }) { cache.media[index].uploaded = true }
            persist()
        }
        cache.dirty.remove(inspection.id); persist()
    }
    func refresh() async throws {
        let remote = try JSONDecoder().decode([Inspection].self, from: await api.request("/inspections"))
        for inspection in remote where !cache.dirty.contains(inspection.id) {
            if let i = cache.inspections.firstIndex(where: { $0.id == inspection.id }) { cache.inspections[i] = inspection }
            else { cache.inspections.append(inspection) }
        }
        persist()
    }
    func download(_ artifact: Artifact) async throws -> URL {
        let data = try await api.request("/artifacts/\(artifact.id)")
        let folder = directory.appendingPathComponent("exports", isDirectory: true).appendingPathComponent(artifact.id, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let url = folder.appendingPathComponent(URL(fileURLWithPath: artifact.filename).lastPathComponent)
        try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        return url
    }
}
