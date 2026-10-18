import SwiftUI

struct ReportEditor: View {
    @Binding var report: ReportDraft
    private var siteFields: [(String, String)] {
        report.equipment == "SH" ? [("length_ft", "Approx. length (ft)"), ("sections", "Individual sections"),
            ("height_ft", "Max height (ft)"), ("width_ft", "Max width (ft)")] :
            [("length_ft", "Approx. length (ft)"), ("height_ft", "Max height (ft)"),
             ("tie_horizontal", "Horizontal tie spacing"), ("tie_vertical", "Vertical tie spacing"),
             ("planked_levels", "Planked levels"), ("outrigger_levels", "Planked outrigger levels"),
             ("tie_type", "Tie type"), ("dunnage_type", "Dunnage type")]
    }
    var body: some View {
        Form {
            Section("Inspection result") {
                Picker("Result — explicit confirmation", selection: $report.status) {
                    Text("Not confirmed").tag("")
                    Text("Open items").tag("OIs")
                    Text("No open items").tag("No OIs")
                }
                if report.status == "No OIs" && !report.open_items.isEmpty {
                    Text("Remove or resolve the recorded findings before confirming No OIs. The server will reject conflicting results.").foregroundStyle(.red)
                }
            }
            Section("Project and request") {
                TextField("Client", text: $report.client)
                TextField("Project", text: $report.project)
                TextField("Subject project / alternate designation", text: $report.subject_project)
                TextField("Request date · YYYY-MM-DD", text: $report.request_date)
                TextField("Inspection date · YYYY-MM-DD", text: $report.inspection_date)
                TextField("Requested by / company", text: $report.requested_by)
                TextField("Permit", text: $report.permit)
                TextField("Inspection number · e.g. VII", text: $report.inspection_code)
                TextField("Address", text: $report.address, axis: .vertical)
                TextField("Actually inspected locations / extents", text: $report.locations, axis: .vertical)
            }
            Section("Drawing status") {
                drawingPicker("PE drawings on site", selection: $report.drawings_on_site)
                drawingPicker("DOB / SCA approved", selection: $report.drawings_approved)
            }
            Section("Actual attendees") {
                ForEach($report.attendees) { $attendee in
                    VStack {
                        TextField("Name", text: $attendee.name)
                        TextField("Company / agency", text: $attendee.company)
                        TextField("Role · use PE for inspecting engineer", text: $attendee.title)
                    }
                }.onDelete { report.attendees.remove(atOffsets: $0) }
                Button("Add attendee") { report.attendees.append(Attendee()) }
                Text("Template names are not proof of attendance. Identify the inspecting PE.").font(.caption)
            }
            Section("Equipment dimensions and details") {
                ForEach(siteFields, id: \.0) { key, label in
                    TextField(label, text: Binding(get: { report.site[key] ?? "" }, set: { report.site[key] = $0 }))
                }
                Text("Use NA only when you confirm it is not applicable. Unanswered values stay pending.").font(.caption)
            }
            Section("Open items") {
                ForEach($report.open_items) { $finding in
                    VStack {
                        TextField("Location / occurrence", text: $finding.location, axis: .vertical)
                        TextField("Required corrective action", text: $finding.action, axis: .vertical)
                    }
                }.onDelete { report.open_items.remove(atOffsets: $0) }
                Button("Add open item") { report.open_items.append(Finding()) }
                Text("Swipe to remove a finding. No OIs is never inferred from an empty list.").font(.caption)
            }
        }.navigationTitle(report.equipment == "SH" ? "Shed facts" : "Scaffold facts")
    }
    private func drawingPicker(_ label: String, selection: Binding<String>) -> some View {
        Picker(label, selection: selection) {
            Text("Not confirmed").tag("")
            Text("Yes").tag("Yes"); Text("No").tag("No"); Text("NA").tag("NA")
        }
    }
}

struct CodeHit: Decodable, Identifiable {
    var id: String
    var agency: String
    var section: String
    var title: String
    var text: String
    var url: String
    var effective_from: String
    var effective_to: String?
    var retrieval: String
}
struct CodeResponse: Decodable { var mode: String; var results: [CodeHit]; var notice: String }
struct CodeSearchView: View {
    @EnvironmentObject var store: InspectionStore
    var onDate: String
    @State private var query = ""
    @State private var semantic = false
    @State private var response: CodeResponse?
    @State private var busy = false
    var body: some View {
        List {
            Section("Reference library") {
                TextField("Condition or section number", text: $query)
                Toggle("Semantic search · sends query to AI provider", isOn: $semantic)
                Text("Applicable date: \(onDate). Only reviewed sources effective on this date are returned.").font(.caption)
                Button(busy ? "Searching…" : "Search") {
                    Task {
                        busy = true; defer { busy = false }
                        do {
                            let data = try await store.api.json("/codes/search", object: ["query": query, "on_date": onDate, "semantic": semantic])
                            response = try JSONDecoder().decode(CodeResponse.self, from: data)
                        } catch { store.error = error.localizedDescription }
                    }
                }.disabled(busy || query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            if let response {
                Section { Text(response.notice).font(.caption) }
                if response.results.isEmpty { Text("No matching reviewed sections are indexed. No compliance conclusion can be drawn.") }
                ForEach(response.results) { hit in
                    Section {
                        Text("\(hit.agency) · \(hit.section)").font(.headline)
                        Text(hit.title).font(.subheadline)
                        Text(hit.text).textSelection(.enabled)
                        Text("Effective \(hit.effective_from) · \(hit.retrieval)").font(.caption)
                        if let url = URL(string: hit.url), url.scheme == "https" { Link("View authoritative source", destination: url) }
                    }
                }
            }
        }.navigationTitle("Code references")
    }
}
