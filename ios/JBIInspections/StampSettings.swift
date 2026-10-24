import SwiftUI
import PhotosUI

struct StampSettings: View {
    @EnvironmentObject var store: InspectionStore
    @AppStorage("stampOwnerName") private var owner = ""
    @State private var selection: PhotosPickerItem?
    @State private var preview: UIImage?
    @State private var message = ""
    var body: some View {
        Section("Saved PE signature / stamp image") {
            TextField("Engineer name (must match PE attendee)", text: $owner)
            if let preview { Image(uiImage: preview).resizable().scaledToFit().frame(maxHeight: 150) }
            PhotosPicker(selection: $selection, matching: .images) { Label("Choose signature/stamp image", systemImage: "signature") }
            Button("Remove saved signature/stamp", role: .destructive) {
                try? FileManager.default.removeItem(at: store.directory.appendingPathComponent("saved-signature.png"))
                preview = nil; message = "Removed from this phone."
            }.disabled(preview == nil)
            Text("Stored in protected local app storage. Applying it to page 2 of a No OIs PDF requires a separate review confirmation. This is a visual stamp, not a cryptographic digital signature.").font(.caption)
            if !message.isEmpty { Text(message).font(.caption) }
        }
        .onAppear { preview = UIImage(contentsOfFile: store.directory.appendingPathComponent("saved-signature.png").path) }
        .onChange(of: selection) { _, item in
            guard let item else { return }
            Task {
                do {
                    guard let bytes = try await item.loadTransferable(type: Data.self), let image = UIImage(data: bytes), let data = image.pngData() else { throw APIError(message: "Choose a readable image.") }
                    guard data.count <= 4 * 1024 * 1024 else { throw APIError(message: "Choose a cropped stamp image under 4 MB.") }
                    try data.write(to: store.directory.appendingPathComponent("saved-signature.png"), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
                    preview = image; message = "Signature/stamp saved on this phone."; selection = nil
                } catch { message = error.localizedDescription }
            }
        }
    }
}
