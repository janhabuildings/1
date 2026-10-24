import SwiftUI

struct ReportEditor: View {
    @Binding var report: ReportDraft
    private var siteFields: [(String, String)] {
        report.equipment == "OT" ? [] : report.equipment == "SH" ? [("length_ft", "Approx. length (ft)"), ("sections", "Individual sections"),
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
            if report.equipment == "OT" {
                Section("Other inspected item") {
                    Picker("Inspection type", selection: siteBinding("report_type", defaultValue: "Unknown / custom")) {
                        Text("SOE (Support of Excavation)").tag("SOE")
                        Text("Fall Protection").tag("Fall Protection")
                        Text("Fence").tag("Fence")
                        Text("Unknown / custom item").tag("Unknown / custom")
                    }
                    TextField("Item name (for unknown / custom)", text: siteBinding("other_name"))
                    TextField("Description / inspection scope", text: siteBinding("details"), axis: .vertical)
                    Text("Choose Unknown / custom while collecting evidence. Enter the item name when writing the report.").font(.caption)
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
            if report.equipment != "OT" { Section("Equipment dimensions and details") {
                ForEach(siteFields, id: \.0) { key, label in
                    TextField(label, text: Binding(get: { report.site[key] ?? "" }, set: { report.site[key] = $0 }))
                }
                Text("Use NA only when you confirm it is not applicable. Unanswered values stay pending.").font(.caption)
            }
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
        }.navigationTitle(report.displayName + " facts")
    }
    private func siteBinding(_ key: String, defaultValue: String = "") -> Binding<String> {
        Binding(get: { report.site[key] ?? defaultValue }, set: { report.site[key] = $0 })
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
    var url: String?
    var effective_from: String?
    var effective_to: String?
    var retrieval: String
    var verified: Bool?
    var source_pages: [Int]?
    var parent_sections: [String]?
}
struct CodeResponse: Decodable { var mode: String; var results: [CodeHit]; var notice: String }
struct CodeSearchView: View {
    @EnvironmentObject var store: InspectionStore
    var onDate: String
    @State private var query = ""
    @State private var semantic = false
    @State private var library = "reviewed"
    @State private var response: CodeResponse?
    @State private var busy = false
    var body: some View {
        List {
            Section("Reference library") {
                Picker("Library", selection: $library) {
                    Text("Reviewed sources").tag("reviewed")
                    Text("NYC DOB Chapter 33 · draft").tag("chapter33")
                    Text("NYC SCA Safety Manual · draft").tag("sca-manual")
                }.disabled(busy)
                TextField("Condition or section number", text: $query)
                Toggle("Semantic search · sends query to AI provider", isOn: $semantic)
                if library == "reviewed" {
                    Text("Applicable date: \(onDate). Only reviewed sources effective on this date are returned.").font(.caption)
                } else {
                    Text("Uploaded draft reference. Source edition and effective dates have not been reviewed; results are not filtered by date.").font(.caption).foregroundStyle(.orange)
                }
                Button(busy ? "Searching…" : "Search") {
                    Task {
                        busy = true; defer { busy = false }
                        do {
                            let endpoint = library == "reviewed" ? "/codes/search" : "/codes/draft/search"
                            let data = try await store.api.json(endpoint, object: ["query": query, "on_date": onDate, "semantic": semantic, "library": library])
                            response = try JSONDecoder().decode(CodeResponse.self, from: data)
                        } catch { store.error = error.localizedDescription }
                    }
                }.disabled(busy || query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            if let response {
                Section { Text(response.notice).font(.caption) }
                if response.results.isEmpty { Text("No matching sections in this library. No compliance conclusion can be drawn.") }
                ForEach(response.results) { hit in
                    Section {
                        Text("\(hit.agency) · \(hit.section)").font(.headline)
                        Text(hit.title).font(.subheadline)
                        Text(hit.text).textSelection(.enabled)
                        if hit.verified == false {
                            Text("DRAFT · PDF pages \((hit.source_pages ?? []).map(String.init).joined(separator: ", ")) · \(hit.retrieval)").font(.caption).foregroundStyle(.orange)
                            if let parents = hit.parent_sections, !parents.isEmpty {
                                Text("Parent sections: \(parents.joined(separator: ", "))").font(.caption)
                            }
                        } else {
                            Text("Effective \(hit.effective_from ?? "unconfirmed") · \(hit.retrieval)").font(.caption)
                        }
                        if let source = hit.url, let url = URL(string: source), url.scheme == "https" { Link("View authoritative source", destination: url) }
                    }
                }
            }
        }.navigationTitle("Code references")
            .onChange(of: library) { _, _ in response = nil }
    }
}
