import SwiftUI
import QuickLook
import PhotosUI
import AVFoundation
import MessageUI
import UniformTypeIdentifiers
import ImageIO

struct ReportRoute: Hashable { let equipment: String }

struct SharedItems: Identifiable { let id = UUID(); var items: [Any] }
struct MailAttachment { var data: Data; var filename: String }
struct MailPayload: Identifiable { let id = UUID(); var subject: String; var html: String; var attachments: [MailAttachment]; var sender: String; var to: [String]; var cc: [String] }

struct InspectionList: View {
    @EnvironmentObject var store: InspectionStore
    @State private var settings = false
    @State private var syncing = false
    @State private var deleteInspectionID: String?
    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Capture on site. Review findings before preparing reports.")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
                ForEach(store.cache.inspections) { inspection in
                    NavigationLink(value: inspection.id) {
                        VStack(alignment: .leading) {
                            Text(inspection.title).font(.headline)
                            Text("\(inspection.project) · \(inspection.inspection_date)").font(.caption)
                            if store.cache.dirty.contains(inspection.id) { Label("Saved on this phone · not synced", systemImage: "iphone").font(.caption).foregroundStyle(.secondary) }
                        }
                    }.swipeActions {
                        Button("Delete", role: .destructive) { deleteInspectionID = inspection.id }
                    }
                }
            }
            .confirmationDialog("Delete this inspection and its evidence on all synced devices?", isPresented: Binding(get: { deleteInspectionID != nil }, set: { if !$0 { deleteInspectionID = nil } }), titleVisibility: .visible) {
                Button("Delete inspection", role: .destructive) {
                    if let id = deleteInspectionID {
                        store.removeInspection(id)
                        Task { do { if store.connected { try await store.flushDeletions() } } catch { store.error = "Deleted locally; server deletion is queued until you reconnect." } }
                    }
                    deleteInspectionID = nil
                }
            }
            .task { if store.connected { do { try await store.syncAll() } catch { store.error = "Could not refresh synced inspections: " + error.localizedDescription } } }
            .refreshable { do { try await store.syncAll() } catch { store.error = error.localizedDescription } }
            .overlay { if store.cache.inspections.isEmpty { ContentUnavailableView("Your inspections", systemImage: "building.2", description: Text("Tap + to begin. Photos and notes are saved on your phone.")) } }
            .navigationTitle("JBI Inspections")
            .navigationDestination(for: String.self) { identity in
                if let inspection = store.cache.inspections.first(where: { $0.id == identity }) { InspectionDetail(inspection: inspection) }
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Settings", systemImage: "gear") { settings = true } }
                ToolbarItem(placement: .topBarTrailing) { Button("New inspection", systemImage: "plus") { store.save(Inspection()) } }
                ToolbarItem(placement: .bottomBar) {
                    Button(syncing ? "Refreshing…" : "Sync / refresh inspections", systemImage: "arrow.clockwise") {
                        Task { syncing = true; defer { syncing = false }; do { try await store.syncAll() } catch { store.error = error.localizedDescription } }
                    }.disabled(syncing)
                }
            }
            .sheet(isPresented: $settings) { SettingsView() }
            .alert("Inspection app", isPresented: Binding(get: { store.error != nil }, set: { if !$0 { store.error = nil } })) {
                Button("OK") { store.error = nil }
            } message: { Text(store.error ?? "") }
        }
    }
}

struct SettingsView: View {
    @AppStorage("backendURL") private var backendURL = API.defaultBaseURL
    @AppStorage("draftMailboxEmail") private var draftMailboxEmail = ""
    @AppStorage("draftToEmails") private var draftToEmails = ""
    @AppStorage("draftCCEmails") private var draftCCEmails = ""
    @State private var token = SecureToken.read()
    @State private var result = ""
    @Environment(\.dismiss) var dismiss
    var body: some View {
        NavigationStack {
            Form {
                StampSettings()
                Section("Saved draft email account") {
                    TextField("Draft mailbox / From email", text: $draftMailboxEmail).keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                    TextField("Default To emails (comma separated)", text: $draftToEmails).keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                    TextField("Default Cc emails (comma separated)", text: $draftCCEmails).keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Text("Use an account configured in Apple Mail. Open the draft, verify From, then Cancel → Save Draft to put it in that account’s Drafts folder. Email myself a copy addresses a new message to the saved mailbox; you decide whether to send.").font(.caption)
                }
                Section("Private backend") {
                    TextField("Render backend URL", text: $backendURL).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    SecureField("Backend API token", text: $token).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Button("Save connection") {
                        do { try SecureToken.save(token); result = "Saved. Credentials stay in this phone's Keychain." }
                        catch { result = error.localizedDescription }
                    }
                    Button("Test connection") {
                        Task {
                            do {
                                let data = try await API(baseURL: backendURL, token: token).request("/capabilities")
                                result = "Connected.\n" + (String(data: data, encoding: .utf8) ?? "")
                            } catch { result = error.localizedDescription }
                        }
                    }
                    if !result.isEmpty { Text(result).font(.caption).textSelection(.enabled) }
                }
                Section("What stays under your control") {
                    Text("Capture works offline. Sync uploads the selected inspection and its media to your private backend. AI analysis sends selected text and photos to the configured provider only after confirmation.")
                    Text("Phone and WhatsApp call audio cannot be captured by this app. Import an existing recording or transcript instead.")
                    Text("Mail opens Apple's composer for your configured account. This version does not create remote Gmail drafts automatically.")
                }
            }.navigationTitle("Settings").toolbar { Button("Done") { dismiss() } }
        }
    }
}

struct InspectionDetail: View {
    @AppStorage("draftMailboxEmail") private var draftMailboxEmail = ""
    @AppStorage("draftToEmails") private var draftToEmails = ""
    @AppStorage("draftCCEmails") private var draftCCEmails = ""
    @EnvironmentObject var store: InspectionStore
    @State var inspection: Inspection
    @StateObject private var audio = AudioCapture()
    @Environment(\.scenePhase) private var phase
    @State private var camera = false
    @State private var photoSelection: [PhotosPickerItem] = []
    @State private var importFile = false
    @State private var recordConsent = false
    @State private var aiConsent = false
    @State private var selectedAIPhotos: Set<String> = []
    @State private var busy = false
    @State private var suggestions = ""
    @State private var suggestedFindings: [SuggestedFinding] = []
    @State private var analysisChecks: [String] = []
    @State private var calendarCandidates: CalendarCandidates?
    @State private var selectedCalendarTitle = ""
    @State private var export: ExportResult?
    @State private var share: SharedItems?
    @State private var reportPreviewURL: URL?
    @State private var mail: MailPayload?
    @State private var showText = false
    @State private var status = ""
    @State private var autoSyncTask: Task<Void, Never>?
    @State private var removeMediaID: String?
    @State private var removeReportType: String?
    @State private var removeArtifactID: String?
    @State private var applyStamp = false
    @State private var stampConsent = false
    @State private var deleteThisInspection = false
    @Environment(\.dismiss) private var closeInspection

    var body: some View {
        Form {
            basics
            capture
            media
            Section("Transcript and field notes") {
                Text("Review and correct transcriptions. They do not automatically become inspection findings.").font(.caption).foregroundStyle(.secondary)
                TextEditor(text: $inspection.transcript).frame(minHeight: 120).accessibilityLabel("Conversation transcript")
                TextEditor(text: $inspection.notes).frame(minHeight: 100).accessibilityLabel("Inspector notes")
            }
            reports
            Section("References") {
                NavigationLink("Search OSHA / DOB / SCA library") { CodeSearchView(onDate: inspection.inspection_date) }
            }
            actions
            if !analysisChecks.isEmpty {
                Section("Confirm before using findings") {
                    ForEach(analysisChecks, id: \.self) { Text($0).font(.caption).foregroundStyle(.orange) }
                }
            }
            if !suggestedFindings.isEmpty {
                Section("Review suggested findings") {
                    ForEach(suggestedFindings) { finding in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(finding.observation).font(.headline)
                            Text(finding.location)
                            Text(finding.suggested_action)
                            if !finding.source_quote.isEmpty { Text("Source: \(finding.source_quote)").font(.caption) }
                            ForEach(finding.uncertainties ?? [], id: \.self) { check in
                                Text("Field confirmation: \(check)").font(.caption).foregroundStyle(.orange)
                            }
                            ForEach(finding.references) { reference in
                                Text("Reference for review: \(reference.agency) \(reference.section)").font(.caption)
                                Text(reference.quote).font(.caption).italic()
                                if reference.verified == false {
                                    Text("DRAFT · PDF pages \((reference.source_pages ?? []).map(String.init).joined(separator: ", ")) · applicability unverified").font(.caption).foregroundStyle(.orange)
                                }
                                if let source = reference.url, let url = URL(string: source), url.scheme == "https" { Link("Verify code source and applicability", destination: url) }
                            }
                            if let photo = finding.photo_id {
                                Text("Photo: \(photo)").font(.caption2)
                                if let item = store.cache.media.first(where: { $0.id == photo }),
                                   let image = evidenceImage(store.mediaURL(item).path) {
                                    Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 160)
                                }
                            }
                            if ["SF", "SH", "OT"].contains(finding.equipment) {
                                Button("Confirm and add as \(finding.equipment == "SF" ? "scaffold" : finding.equipment == "SH" ? "shed" : "Other") open item") {
                                    adopt(finding)
                                }
                            } else { Text("Equipment is unclear; add this manually after clarification.").font(.caption) }
                        }
                    }
                }
            }
            if let export { artifacts(export) }
            if !suggestions.isEmpty {
                Section("Candidates and analysis details") {
                    Text(suggestions).font(.caption).textSelection(.enabled)
                    if calendarCandidates != nil {
                        Button("Fill missing fields again") { applyCalendar() }
                    }
                }
            }
            if !status.isEmpty { Section { Text(status).font(.caption).textSelection(.enabled) } }
        }
        .navigationTitle(inspection.project.isEmpty ? "Inspection" : inspection.project)
        .navigationDestination(for: ReportRoute.self) { route in
            ReportFactsEditor(reports: $inspection.reports, project: inspection.project, inspectionDate: inspection.inspection_date, initialEquipment: route.equipment)
        }
        .onChange(of: inspection) { _, value in store.save(value); scheduleSync() }
        .onChange(of: phase) { _, value in if value != .active { finishRecording() } }
        .onDisappear { finishRecording() }
        .onChange(of: photoSelection) { _, items in
            guard !items.isEmpty else { return }
            Task {
                for item in items {
                    guard store.cache.inspections.contains(where: { $0.id == inspection.id }) else { break }
                    do {
                        if let data = try await item.loadTransferable(type: Data.self), let image = UIImage(data: data) { savePhoto(image) }
                    } catch { store.error = error.localizedDescription }
                }
                photoSelection = []
            }
        }
        .task {
            if store.connected {
                do { export = try JSONDecoder().decode(ExportResult.self, from: await store.api.request("/inspections/\(inspection.id)/artifacts")) } catch { }
            }
        }
        .confirmationDialog(confirmationTitle, isPresented: Binding(get: { confirmationPresented }, set: { if !$0 { clearConfirmation() } }), titleVisibility: .visible) {
            confirmationButtons
        } message: { Text(confirmationMessage) }
        .sheet(isPresented: $camera) { CameraView(captured: savePhoto).ignoresSafeArea() }
        .sheet(item: $share) { ShareSheet(items: $0.items) }
        .quickLookPreview($reportPreviewURL)
        .sheet(item: $mail) { MailDraft(subject: $0.subject, html: $0.html, attachments: $0.attachments, sender: $0.sender, to: $0.to, cc: $0.cc) }
        .sheet(isPresented: $showText) { TextDraft(body: "\(inspection.project) — inspection \(inspection.inspection_date)\n\(inspection.notes)") }
        .fileImporter(isPresented: $importFile, allowedContentTypes: [.audio, .plainText], allowsMultipleSelection: false, onCompletion: importMedia)
    }
    private var confirmationPresented: Bool {
        deleteThisInspection || removeMediaID != nil || removeReportType != nil || removeArtifactID != nil || stampConsent || recordConsent || aiConsent
    }
    private var confirmationTitle: String {
        if deleteThisInspection { return "Delete this inspection and its evidence on all synced devices?" }
        if removeMediaID != nil { return "Remove this evidence from the inspection?" }
        if removeReportType != nil { return "Remove this report from the inspection?" }
        if removeArtifactID != nil { return "Delete this generated file?" }
        if stampConsent { return "Apply your saved signature/stamp to No OIs PDFs?" }
        if recordConsent { return "Record this conversation?" }
        return "Send inspection data for AI analysis?"
    }
    private var confirmationMessage: String {
        if stampConsent { return "Review the unsigned report first. Your image is placed on page 2 only for No OIs PDFs and its engineer must match an actual PE attendee. This is not a cryptographic digital signature." }
        if recordConsent { return "Record only after participants are informed and consent requirements are met. Recording stops when you leave this screen or the app becomes inactive." }
        if aiConsent { return "Calendar, notes, transcript and up to six selected photos are sent to the configured AI provider. Draft DOB/SCA references and findings require your review." }
        return "Deletion of synced inspection data is shared with other devices."
    }
    private func clearConfirmation() {
        deleteThisInspection = false; removeMediaID = nil; removeReportType = nil; removeArtifactID = nil
        stampConsent = false; recordConsent = false; aiConsent = false
    }
    @ViewBuilder private var confirmationButtons: some View {
        if deleteThisInspection {
            Button("Delete inspection", role: .destructive) {
                autoSyncTask?.cancel(); store.removeInspection(inspection.id); closeInspection()
                Task { do { if store.connected { try await store.flushDeletions() } } catch { store.error = "Deleted locally; server deletion queued until reconnect." } }
            }
        } else if let id = removeMediaID {
            Button("Delete evidence", role: .destructive) {
                store.removeMedia(id); selectedAIPhotos.remove(id)
                for i in inspection.reports.indices { inspection.reports[i].photo_references.removeAll { $0 == id } }
                scheduleSync()
            }
        } else if let type = removeReportType {
            Button("Remove report", role: .destructive) { inspection.reports.removeAll { $0.equipment == type } }
        } else if let id = removeArtifactID {
            Button("Delete file", role: .destructive) {
                Task {
                    do {
                        _ = try await store.api.request("/artifacts/\(id)", method: "DELETE")
                        export?.artifacts.removeAll { $0.id == id }
                        try? FileManager.default.removeItem(at: store.directory.appendingPathComponent("exports").appendingPathComponent(id))
                        store.cache.artifactOwners?.removeValue(forKey: id); store.persist()
                    } catch { store.error = error.localizedDescription }
                }
            }
        } else if stampConsent {
            Button("I reviewed the report and authorize this stamp") { generate(stampApproved: true) }
        } else if recordConsent {
            Button("Participants informed — start recording") { Task { do { try await audio.start() } catch { store.error = error.localizedDescription } } }
        } else if aiConsent {
            Button("Send notes, transcript and up to six photos") { analyze() }
        }
        Button("Cancel", role: .cancel) { clearConfirmation() }
    }
    private var basics: some View {
        Section("Inspection") {
            TextField("Title", text: $inspection.title)
            TextField("Project", text: $inspection.project)
            if let project = calendarCandidates?.fields["project"], !project.isEmpty, project != inspection.project {
                Button("Use calendar project: " + project) {
                    let previous = inspection.project
                    inspection.project = project
                    for index in inspection.reports.indices where inspection.reports[index].project.isEmpty || inspection.reports[index].project == previous {
                        inspection.reports[index].project = project
                    }
                    store.save(inspection)
                }
            }
            TextField("Inspection date · YYYY-MM-DD", text: $inspection.inspection_date)
            Text("Paste the complete calendar entry below.").font(.caption)
            TextEditor(text: $inspection.calendar_text).frame(minHeight: 140).accessibilityLabel("Calendar content")
            Button("Extract calendar candidates") { extract() }.disabled(busy)
            if let titles = calendarCandidates?.titles, !titles.isEmpty {
                Picker("Inspection title from calendar", selection: $selectedCalendarTitle) {
                    Text("Choose a title…").tag("")
                    ForEach(titles, id: \.self) { title in Text(title).tag(title) }
                }.pickerStyle(.menu)
                    .onChange(of: selectedCalendarTitle) { _, title in
                        if !title.isEmpty { inspection.title = title; store.save(inspection) }
                    }
                Text("Choose a title when several are listed. Calendar dates fill on extraction. Review the dates and confirm the report outcome separately.").font(.caption)
            }
        }
    }
    private var capture: some View {
        Section("Capture") {
            Button("Take inspection photo", systemImage: "camera") {
                guard UIImagePickerController.isSourceTypeAvailable(.camera) else { store.error = "A physical iPhone camera is required."; return }
                AVCaptureDevice.requestAccess(for: .video) { granted in
                    Task { @MainActor in if granted { camera = true } else { store.error = "Enable camera permission in iPhone Settings." } }
                }
            }
            PhotosPicker(selection: $photoSelection, maxSelectionCount: 100, matching: .images) { Label("Import photos", systemImage: "photo") }
            Button(audio.recording ? "Stop recording" : "Record on-site conversation", systemImage: audio.recording ? "stop.circle.fill" : "mic") {
                if audio.recording { finishRecording() } else { recordConsent = true }
            }.foregroundStyle(audio.recording ? Color.red : Color.accentColor)
            if audio.recording { Label("Recording in progress", systemImage: "waveform").foregroundStyle(.red) }
            Button("Import audio or a transcript", systemImage: "square.and.arrow.down") { importFile = true }
        }
    }
    private var media: some View {
        Section("Photo and audio evidence") {
            ForEach(store.cache.media.filter { $0.inspectionID == inspection.id }) { item in
                VStack(alignment: .leading, spacing: 8) {
                    if item.kind == "photo", let image = evidenceImage(store.mediaURL(item).path) {
                        Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 180)
                        Toggle("Include photo in AI review", isOn: Binding(
                            get: { selectedAIPhotos.contains(item.id) },
                            set: { value in
                                if value { selectedAIPhotos.insert(item.id) } else { selectedAIPhotos.remove(item.id) }
                            }))
                    } else { Label("Audio recording", systemImage: "waveform") }
                    Picker("Equipment", selection: mediaBinding(item.id, \.equipment)) {
                        Text("Not assigned").tag(""); Text("Scaffold").tag("SF"); Text("Shed").tag("SH"); Text("Other").tag("OT")
                    }
                    TextField("Location / observation", text: mediaBinding(item.id, \.note), axis: .vertical)
                        .onChange(of: item.note) { _, _ in store.cache.dirty.insert(inspection.id); store.persist(); scheduleSync() }
                        .onChange(of: item.equipment) { _, _ in store.cache.dirty.insert(inspection.id); store.persist(); scheduleSync() }
                    if item.kind == "photo" || item.kind == "audio" {
                        Button("Delete evidence", role: .destructive) { removeMediaID = item.id }.buttonStyle(.borderless)
                    }
                    HStack {
                        Button("Share") { share = SharedItems(items: [store.mediaURL(item)]) }.buttonStyle(.borderless)
                        if item.kind == "audio" {
                            Button(audio.transcribing ? "Transcribing…" : "Transcribe on device") {
                                Task {
                                    do {
                                        let text = try await audio.transcribe(store.mediaURL(item))
                                        inspection.transcript += (inspection.transcript.isEmpty ? "" : "\n\n") + text
                                    } catch { store.error = error.localizedDescription }
                                }
                            }.disabled(audio.transcribing).buttonStyle(.borderless)
                        }
                    }
                    Text(item.uploaded ? "Uploaded to backend" : "Saved on this phone").font(.caption).foregroundStyle(.secondary)
                }
            }
        }.onChange(of: store.cache.media) { _, _ in store.cache.dirty.insert(inspection.id); store.persist() }
    }
    private var reports: some View {
        Section("Report facts — inspector review") {
            ForEach(inspection.reports) { report in
                HStack {
                    NavigationLink(report.displayName + " report", value: ReportRoute(equipment: report.equipment))
                    CompactRemoveButton(label: "Remove report") { removeReportType = report.equipment }
                }
            }
            if !inspection.reports.contains(where: { $0.equipment == "SF" }) { Button("Add scaffold report") { addReport("SF") } }
            if !inspection.reports.contains(where: { $0.equipment == "SH" }) { Button("Add shed report") { addReport("SH") } }
            if !inspection.reports.contains(where: { $0.equipment == "OT" }) { Button("Add Other report") { addReport("OT") } }
        }
    }
    private var actions: some View {
        Section("Review and prepare") {
            Button("Sync this inspection", systemImage: "arrow.triangle.2.circlepath") { sync() }.disabled(busy)
            Button("Suggest findings from notes/photos", systemImage: "sparkles") { aiConsent = true }.disabled(busy)
            if inspection.reports.contains(where: { $0.status == "No OIs" }) {
                Toggle("Apply saved signature/stamp to No OIs PDF", isOn: $applyStamp)
            }
            Button("Generate review reports", systemImage: "doc.richtext") { if applyStamp && inspection.reports.contains(where: { $0.status == "No OIs" }) { stampConsent = true } else { generate() } }.disabled(busy)
            Button("Share notes to WhatsApp or another app", systemImage: "square.and.arrow.up") {
                share = SharedItems(items: ["\(inspection.project) · \(inspection.inspection_date)\n\(inspection.notes)"])
            }
            Button("Delete inspection", role: .destructive) { deleteThisInspection = true }.disabled(busy)
            Button("Prepare a text message", systemImage: "message") {
                if MFMessageComposeViewController.canSendText() { showText = true }
                else { store.error = "Messages is not configured on this device." }
            }
            Text("You review all messages and choose whether to send. The app cannot read your personal SMS or WhatsApp history.").font(.caption).foregroundStyle(.secondary)
        }
    }
    private func artifacts(_ result: ExportResult) -> some View {
        Section("Generated review files") {
            Text(result.notice).font(.caption)
            Text("Draft mailbox: " + (draftMailboxEmail.isEmpty ? "Not set — add in Settings" : draftMailboxEmail)).font(.caption)
            TextField("To emails (comma separated)", text: $draftToEmails).keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
            TextField("Cc emails (comma separated)", text: $draftCCEmails).keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
            Text("Open in Mail, verify From, then Cancel → Save Draft. Nothing is sent automatically.").font(.caption)
            ForEach(result.artifacts) { artifact in
                VStack(alignment: .leading) {
                    Text(artifact.filename).font(.caption)
                    HStack {
                        Button("Delete", role: .destructive) { removeArtifactID = artifact.id }.buttonStyle(.borderless)
                        if ["application/pdf", "text/html", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"].contains(artifact.mime) {
                            Button("Preview") {
                                Task { do { reportPreviewURL = try await store.download(artifact, inspectionID: inspection.id) } catch { store.error = error.localizedDescription } }
                            }.buttonStyle(.borderless)
                        }
                        Button("Open / share") {
                            Task { do { share = SharedItems(items: [try await store.download(artifact, inspectionID: inspection.id)]) } catch { store.error = error.localizedDescription } }
                        }.buttonStyle(.borderless)
                        if artifact.mime == "text/html" {
                            Button("Open draft in Mail") { compose(artifact, artifacts: result.artifacts) }.buttonStyle(.borderless)
                            Button("Email myself a copy") { compose(artifact, artifacts: result.artifacts, toMyself: true) }.buttonStyle(.borderless).disabled(draftMailboxEmail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        }
                    }
                }
            }
            if let data = try? JSONEncoder().encode(result.reports), let text = String(data: data, encoding: .utf8) {
                Text(text).font(.caption2).textSelection(.enabled)
            }
            Text("Check fonts, wrapping and page breaks before delivery. PDFs are review drafts; verify any applied stamp and final layout.").font(.caption).foregroundStyle(.orange)
        }
    }
    private func addReport(_ type: String) {
        var report = ReportDraft(equipment: type)
        report.project = inspection.project; report.inspection_date = inspection.inspection_date
        inspection.reports.append(report)
    }
    private func savePhoto(_ image: UIImage) {
        do {
            guard let data = image.jpegData(compressionQuality: 0.85) else { throw APIError(message: "Could not encode photo.") }
            try store.addMedia(data, to: inspection, kind: "photo", mime: "image/jpeg", ext: "jpg"); scheduleSync()
        } catch { store.error = error.localizedDescription }
    }
    private func finishRecording() {
        guard let url = audio.stop() else { return }
        do {
            try store.addMedia(Data(contentsOf: url), to: inspection, kind: "audio", mime: "audio/mp4", ext: "m4a")
            try? FileManager.default.removeItem(at: url); scheduleSync()
        } catch { store.error = error.localizedDescription }
    }
    private func importMedia(_ result: Result<[URL], Error>) {
        do {
            guard let url = try result.get().first else { return }
            let access = url.startAccessingSecurityScopedResource(); defer { if access { url.stopAccessingSecurityScopedResource() } }
            let data = try Data(contentsOf: url)
            guard data.count <= 40 * 1024 * 1024 else { throw APIError(message: "Import limit is 40 MB.") }
            let ext = url.pathExtension.lowercased()
            if ext == "txt" {
                guard let text = String(data: data, encoding: .utf8) else { throw APIError(message: "Use a UTF-8 transcript file.") }
                inspection.transcript += (inspection.transcript.isEmpty ? "" : "\n\n") + text
            } else {
                let types = ["m4a": "audio/mp4", "wav": "audio/wav", "mp3": "audio/mpeg"]
                guard let mime = types[ext] else { throw APIError(message: "Import M4A, WAV, MP3 or UTF-8 TXT.") }
                try store.addMedia(data, to: inspection, kind: "audio", mime: mime, ext: ext); scheduleSync()
            }
        } catch { store.error = error.localizedDescription }
    }
    private func evidenceImage(_ path: String) -> UIImage? {
        guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 1000, kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary) else { return nil }
        return UIImage(cgImage: image)
    }
    private func mediaBinding(_ id: String, _ key: WritableKeyPath<LocalMedia, String>) -> Binding<String> {
        Binding(get: { store.cache.media.first(where: { $0.id == id })?[keyPath: key] ?? "" }, set: { value in
            if let index = store.cache.media.firstIndex(where: { $0.id == id }) { store.cache.media[index][keyPath: key] = value }
        })
    }
    private func scheduleSync() {
        autoSyncTask?.cancel()
        guard store.connected else { status = "Saved on this phone. Configure the backend to sync."; return }
        autoSyncTask = Task {
            do {
                try await Task.sleep(for: .seconds(2))
                guard !Task.isCancelled, !busy else { return }
                try await store.sync(inspection)
                if !Task.isCancelled && !store.cache.dirty.contains(inspection.id) { status = "Synced to backend. Use Refresh saved on the website to see updates." }
            } catch is CancellationError { }
            catch { if !Task.isCancelled { status = "Saved on this phone; sync failed: " + error.localizedDescription } }
        }
    }
    private func sync() {
        autoSyncTask?.cancel()
        Task { busy = true; defer { busy = false }; do { store.save(inspection); try await store.sync(inspection); status = "Inspection and media synced." } catch { store.error = error.localizedDescription } }
    }
    private func extract() {
        Task {
            busy = true; defer { busy = false }
            do {
                let data = try await store.api.json("/calendar/extract", object: ["text": inspection.calendar_text])
                calendarCandidates = try JSONDecoder().decode(CalendarCandidates.self, from: data)
                let titles = calendarCandidates?.titles ?? []
                selectedCalendarTitle = titles.contains(inspection.title) ? inspection.title : (titles.count == 1 ? titles[0] : "")
                // No outcome or drawing approval is inferred.
                let object = try JSONSerialization.jsonObject(with: data)
                let pretty = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
                suggestions = String(data: pretty, encoding: .utf8) ?? ""
                applyCalendar(clearCandidates: false, applyDates: true)
                store.save(inspection)
                scheduleSync()
                status = "Calendar details filled and saved on this phone. Review the fields and choose a title if several are listed. Calendar inspection and request dates were filled; other existing facts were kept."
            } catch { store.error = error.localizedDescription }
        }
    }
    private func calendarFieldMissing(_ value: String) -> Bool {
        ["", "[pending confirmation]", "pending", "tbd"].contains(value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
    }
    private func applyCalendar(clearCandidates: Bool = true, applyDates: Bool = false) {
        guard let candidates = calendarCandidates else { return }
        if !selectedCalendarTitle.isEmpty { inspection.title = selectedCalendarTitle }
        if let value = candidates.fields["project"], calendarFieldMissing(inspection.project) { inspection.project = value }
        if let value = candidates.fields["inspection_date"], applyDates || calendarFieldMissing(inspection.inspection_date) { inspection.inspection_date = value }
        for item in candidates.equipment {
            if let equipment = item["equipment"], !inspection.reports.contains(where: { $0.equipment == equipment }) { addReport(equipment) }
        }
        for index in inspection.reports.indices {
            if calendarFieldMissing(inspection.reports[index].client) { inspection.reports[index].client = candidates.fields["client"] ?? "" }
            if calendarFieldMissing(inspection.reports[index].project) { inspection.reports[index].project = candidates.fields["project"] ?? inspection.project }
            if calendarFieldMissing(inspection.reports[index].requested_by) { inspection.reports[index].requested_by = candidates.fields["requested_by"] ?? "" }
            if calendarFieldMissing(inspection.reports[index].address) { inspection.reports[index].address = candidates.fields["address"] ?? "" }
            if let date = candidates.fields["request_date"], applyDates || calendarFieldMissing(inspection.reports[index].request_date) { inspection.reports[index].request_date = date }
            if (applyDates && candidates.fields["inspection_date"] != nil) || calendarFieldMissing(inspection.reports[index].inspection_date) { inspection.reports[index].inspection_date = inspection.inspection_date }
            if calendarFieldMissing(inspection.reports[index].drawings_on_site) { inspection.reports[index].drawings_on_site = candidates.fields["drawings_on_site"] ?? "" }
            if calendarFieldMissing(inspection.reports[index].drawings_approved) { inspection.reports[index].drawings_approved = candidates.fields["drawings_approved"] ?? "" }
            if inspection.reports.count == 1 && calendarFieldMissing(inspection.reports[index].permit) { inspection.reports[index].permit = candidates.fields["permit"] ?? "" }
            if let item = candidates.equipment.first(where: { $0["equipment"] == inspection.reports[index].equipment }) {
                if calendarFieldMissing(inspection.reports[index].permit) { inspection.reports[index].permit = item["permit"] ?? "" }
                if calendarFieldMissing(inspection.reports[index].inspection_code) { inspection.reports[index].inspection_code = item["inspection_code"] ?? "" }
                if calendarFieldMissing(inspection.reports[index].subject_project) { inspection.reports[index].subject_project = item["subject_project"] ?? "" }
                for key in ["report_type", "other_name"] {
                    if let value = item[key], calendarFieldMissing(inspection.reports[index].site[key] ?? "") { inspection.reports[index].site[key] = value }
                }
            }
        }
        if clearCandidates { calendarCandidates = nil }
        store.save(inspection)
        status = "Calendar details filled and saved. Review dates, result and drawing status."
    }
    private func analyze() {
        suggestedFindings = []; analysisChecks = []
        Task {
            busy = true; defer { busy = false }
            do {
                guard selectedAIPhotos.count <= 6 else { throw APIError(message: "Select at most six photos for AI review.") }
                store.save(inspection); try await store.sync(inspection)
                let ids = store.cache.media.filter { $0.inspectionID == inspection.id && $0.kind == "photo" && selectedAIPhotos.contains($0.id) }.map(\.id)
                let data = try await store.api.json("/inspections/\(inspection.id)/analyze", object: ["consent": true, "media_ids": Array(ids)])
                let analysis = try JSONDecoder().decode(AISuggestionResponse.self, from: data).suggestions
                suggestedFindings = analysis.suggested_findings
                analysisChecks = Array(Set(analysis.warnings + analysis.missing_information)).sorted()
                if suggestedFindings.isEmpty { analysisChecks.append("No findings suggested. This does not establish No OIs.") }
                suggestions = ""
            } catch { store.error = error.localizedDescription }
        }
    }
    private func adopt(_ finding: SuggestedFinding) {
        if !inspection.reports.contains(where: { $0.equipment == finding.equipment }) { addReport(finding.equipment) }
        guard let index = inspection.reports.firstIndex(where: { $0.equipment == finding.equipment }) else { return }
        inspection.reports[index].status = "OIs"
        inspection.reports[index].open_items.append(Finding(location: finding.location, action: finding.suggested_action))
        if let photo = finding.photo_id { inspection.reports[index].photo_references.append(photo) }
        inspection.reports[index].source_references.append(finding.source_quote)
        for reference in finding.references {
            let status = reference.verified == false ? "DRAFT; applicability unverified" : "Reference for review"
            let pages = (reference.source_pages ?? []).map(String.init).joined(separator: ", ")
            inspection.reports[index].source_references.append("\(status): \(reference.agency) \(reference.section) · PDF pages \(pages) · \(reference.url ?? reference.document ?? "Uploaded source") · \(reference.quote)")
        }
        suggestedFindings.removeAll { $0.id == finding.id }
    }
    private func generate(stampApproved: Bool = false) {
        autoSyncTask?.cancel()
        Task {
            busy = true; defer { busy = false }
            do {
                for index in inspection.reports.indices {
                    let equipment = inspection.reports[index].equipment
                    let refs = store.cache.media.filter { $0.inspectionID == inspection.id && $0.kind == "photo" && $0.equipment == equipment }.map(\.id)
                    inspection.reports[index].photo_references = Array(Set(inspection.reports[index].photo_references + refs))
                }
                store.save(inspection); try await store.sync(inspection)
                var options: [String: Any] = [:]
                if !draftMailboxEmail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { options["mailbox_email"] = draftMailboxEmail.trimmingCharacters(in: .whitespacesAndNewlines) }
                if stampApproved {
                    let owner = UserDefaults.standard.string(forKey: "stampOwnerName") ?? ""
                    guard !owner.trimmingCharacters(in: .whitespaces).isEmpty else { throw APIError(message: "Enter the stamp engineer name in Settings.") }
                    let path = store.directory.appendingPathComponent("saved-signature.png")
                    guard FileManager.default.fileExists(atPath: path.path) else { throw APIError(message: "Choose your signature/stamp image in Settings first.") }
                    let encoded = owner.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed.subtracting(CharacterSet(charactersIn: "&+=?#"))) ?? ""
                    let stamp = try JSONDecoder().decode(StampAsset.self, from: await store.api.request("/signing-assets?owner=\(encoded)", method: "POST", body: Data(contentsOf: path), mime: "image/png"))
                    options["stamp_id"] = stamp.id; options["stamp_reviewed"] = true
                }
                let data = try await store.api.json("/inspections/\(inspection.id)/reports", object: options)
                export = try JSONDecoder().decode(ExportResult.self, from: data)
            } catch { store.error = error.localizedDescription }
        }
    }
    private func compose(_ htmlArtifact: Artifact, artifacts: [Artifact], toMyself: Bool = false) {
        guard MFMailComposeViewController.canSendMail() else { store.error = "Configure an account in Apple's Mail app to use the HTML composer. You can still share the generated files."; return }
        Task {
            do {
                let url = try await store.download(htmlArtifact, inspectionID: inspection.id)
                let html = try String(contentsOf: url, encoding: .utf8)
                var attachments: [MailAttachment] = []
                for artifact in artifacts where artifact.equipment == htmlArtifact.equipment && artifact.generation_id == htmlArtifact.generation_id && artifact.mime == "application/pdf" {
                    let file = try await store.download(artifact, inspectionID: inspection.id)
                    let data = try Data(contentsOf: file)
                    guard data.starts(with: Data("%PDF-".utf8)) else { throw APIError(message: "The report attachment is not a valid PDF.") }
                    attachments.append(MailAttachment(data: data, filename: artifact.filename))
                }
                let subject = htmlArtifact.filename.replacingOccurrences(of: " - DRAFT.html", with: "").replacingOccurrences(of: " - Cover.html", with: "")
                let sender = draftMailboxEmail.trimmingCharacters(in: .whitespacesAndNewlines)
                func addresses(_ text: String) throws -> [String] {
                    let values = text.split(whereSeparator: { $0 == "," || $0 == ";" }).map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
                    guard values.allSatisfy({ $0.range(of: #"^[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+$"#, options: .regularExpression) != nil }) else { throw APIError(message: "Check the email addresses in Settings / draft recipients.") }
                    return values
                }
                let senderAddresses = try addresses(sender)
                guard senderAddresses.count <= 1 else { throw APIError(message: "Enter one draft mailbox email in Settings.") }
                let recipients = try addresses(toMyself ? sender : draftToEmails)
                let copies = try addresses(toMyself ? "" : draftCCEmails)
                mail = MailPayload(subject: subject, html: html, attachments: attachments, sender: sender, to: recipients, cc: copies)
            } catch { store.error = error.localizedDescription }
        }
    }
}
