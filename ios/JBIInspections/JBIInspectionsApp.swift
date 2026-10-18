import SwiftUI

@main struct JBIInspectionsApp: App {
    @StateObject private var store = InspectionStore()
    var body: some Scene {
        WindowGroup { InspectionList().environmentObject(store) }
    }
}
