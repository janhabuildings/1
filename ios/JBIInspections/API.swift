import Foundation
import Security

struct APIError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}
enum SecureToken {
    static let service = "nyc.dseny.inspections.backend"
    static func read() -> String {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service, kSecAttrAccount as String: "api-token",
            kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return "" }
        return String(data: data, encoding: .utf8) ?? ""
    }
    static func save(_ value: String) throws {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service, kSecAttrAccount as String: "api-token"]
        SecItemDelete(query as CFDictionary)
        var item = query
        item[kSecValueData as String] = Data(value.utf8)
        item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else {
            throw APIError(message: "Could not save the backend credential in Keychain.")
        }
    }
}
struct API {
    static let defaultBaseURL = "https://jbi-inspections.onrender.com"
    let baseURL: String
    let token: String
    func request(_ path: String, method: String = "GET", body: Data? = nil,
                 mime: String = "application/json", headers: [String: String] = [:]) async throws -> Data {
        guard let base = URL(string: baseURL), base.scheme == "https" ||
                (base.scheme == "http" && ["localhost", "127.0.0.1"].contains(base.host ?? "")),
              let url = URL(string: path, relativeTo: base) else {
            throw APIError(message: "Enter an HTTPS backend URL in Settings.")
        }
        guard !token.isEmpty else { throw APIError(message: "Set the backend API token in Settings.") }
        var req = URLRequest(url: url)
        req.httpMethod = method; req.httpBody = body; req.timeoutInterval = path.hasSuffix("/analyze") ? 360 : 180
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue(mime, forHTTPHeaderField: "Content-Type")
        headers.forEach { req.setValue($0.value, forHTTPHeaderField: $0.key) }
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw APIError(message: "No backend response.") }
        guard (200..<300).contains(http.statusCode) else {
            let detail = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            throw APIError(message: (detail?["detail"] as? String) ?? "Backend returned HTTP \(http.statusCode).")
        }
        return data
    }
    func json(_ path: String, method: String = "POST", object: Any) async throws -> Data {
        try await request(path, method: method, body: JSONSerialization.data(withJSONObject: object))
    }
}
