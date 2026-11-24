import SwiftUI

// Replacing the entire store keeps pending work tied to its original account,
// credentials and private directory, even if a previous task finishes later.
@MainActor final class AccountSession: ObservableObject {
    @Published var store = InspectionStore()
    @Published var generation = UUID()
    @Published private(set) var connecting = false
    func connect(baseURL: String, token: String) async throws {
        guard !connecting else { return }
        connecting = true; defer { connecting = false }
        let data = try await API(baseURL: baseURL, token: token).request("/workspace/me")
        guard let user = try JSONSerialization.jsonObject(with: data) as? [String: Any], let id = user["id"] as? String else {
            throw APIError(message: "The backend did not return an account identity.")
        }
        let defaults = UserDefaults.standard
        let keys = ["stampOwnerName", "draftMailboxEmail", "draftToEmails", "draftCCEmails"]
        let previousPreferences = keys.reduce(into: [String: String]()) { $0[$1] = defaults.string(forKey: $1) ?? "" }
        defaults.set(previousPreferences, forKey: "accountPreferences:" + store.directory.path)
        try SecureToken.save(token)
        UserDefaults.standard.set(baseURL, forKey: "backendURL")
        UserDefaults.standard.set(id, forKey: "workspaceAccountID")
        UserDefaults.standard.set(user["name"] as? String ?? "", forKey: "workspaceAccountName")
        store.persist()
        store = InspectionStore(baseURL: baseURL, token: token, accountID: id)
        let preferences = defaults.dictionary(forKey: "accountPreferences:" + store.directory.path) as? [String: String] ?? [:]
        for key in keys { defaults.set(preferences[key] ?? "", forKey: key) }
        generation = UUID()
    }
    func signOut() throws {
        store.persist()
        let keys = ["stampOwnerName", "draftMailboxEmail", "draftToEmails", "draftCCEmails"]
        let preferences = keys.reduce(into: [String: String]()) { $0[$1] = UserDefaults.standard.string(forKey: $1) ?? "" }
        UserDefaults.standard.set(preferences, forKey: "accountPreferences:" + store.directory.path)
        for key in keys { UserDefaults.standard.removeObject(forKey: key) }
        try SecureToken.save("")
        UserDefaults.standard.set("signed-out", forKey: "workspaceAccountID")
        UserDefaults.standard.set("Signed out", forKey: "workspaceAccountName")
        store = InspectionStore(token: "", accountID: "signed-out")
        generation = UUID()
    }
}

@main struct JBIInspectionsApp: App {
    @StateObject private var account = AccountSession()
    var body: some Scene {
        WindowGroup {
            InspectionList().id(account.generation).environmentObject(account.store).environmentObject(account)
        }
    }
}
