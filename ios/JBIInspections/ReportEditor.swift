import SwiftUI

enum AttendeeOptions {
    static let roles = ["Competent Person/Site Supervisor", "Safety Inspector", "Competent Person/ Equipment Installation Supervisor", "Competent Person", "GC’s Project Manager", "CM’s Representative", "Owner’s Representative", "PE"]
    static let companies = ["NYC SCA", "DSENY Engineering Services PC"]
}

struct ReportFactsEditor: View {
    @Binding var reports: [ReportDraft]
    var project: String
    var inspectionDate: String
    @State private var selectedEquipment: String
    init(reports: Binding<[ReportDraft]>, project: String, inspectionDate: String, initialEquipment: String) {
        _reports = reports; self.project = project; self.inspectionDate = inspectionDate
        _selectedEquipment = State(initialValue: initialEquipment)
    }
    private var selection: Binding<String> {
        Binding(get: { selectedEquipment }, set: { equipment in
            UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
            if !reports.contains(where: { $0.equipment == equipment }) {
                if let index = reports.firstIndex(where: { $0.equipment == selectedEquipment }) {
                    reports[index].equipment = equipment
                } else {
                    var draft = ReportDraft(equipment: equipment)
                    draft.project = project; draft.inspection_date = inspectionDate
                    reports.append(draft)
                }
            }
            selectedEquipment = equipment
        })
    }
    var body: some View {
        let equipment = selectedEquipment
        ReportEditor(report: Binding(get: { reports.first(where: { $0.equipment == equipment }) ?? ReportDraft(equipment: equipment) }, set: { value in
            if let index = reports.firstIndex(where: { $0.equipment == equipment }) { reports[index] = value }
        }), reportSelection: selection).id(equipment)
    }
}

struct MultiChoiceField: View {
    var label: String
    @Binding var value: String
    var options: [String]
    var separator = "; "
    @State private var query = ""
    @FocusState private var searching: Bool
    private var selected: [String] {
        value.components(separatedBy: separator == "\n" ? .newlines : CharacterSet(charactersIn: ";\n"))
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
            .reduce(into: [String]()) { result, item in if !result.contains(item) { result.append(item) } }
    }
    private func toggle(_ option: String) {
        var items = selected
        if items.contains(option) { items.removeAll { $0 == option } }
        else {
            if option == "NA" { items.removeAll() } else { items.removeAll { $0 == "NA" } }
            items.append(option)
        }
        value = items.joined(separator: separator)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                TextField(label, text: $query, prompt: Text(label).foregroundStyle(.secondary))
                    .focused($searching)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .accessibilityLabel("Search " + label)
                ForEach(selected, id: \.self) { option in
                    HStack {
                        Text(option).font(.caption).foregroundStyle(.secondary)
                        Spacer(minLength: 8)
                        CompactRemoveButton(label: "Remove " + option) { toggle(option) }
                    }
                }
            }.padding(8)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.secondary.opacity(0.25)))
            if searching {
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(options.filter { query.isEmpty || $0.localizedCaseInsensitiveContains(query) }, id: \.self) { option in
                            Button { toggle(option) } label: {
                                HStack {
                                    Text(option).foregroundStyle(.primary).multilineTextAlignment(.leading)
                                    Spacer(minLength: 8)
                                    if selected.contains(option) { Image(systemName: "checkmark").foregroundStyle(.tint) }
                                }.padding(.vertical, 9).contentShape(Rectangle())
                            }.buttonStyle(.plain)
                                .accessibilityValue(selected.contains(option) ? "Selected" : "Not selected")
                        }
                        let custom = query.trimmingCharacters(in: .whitespacesAndNewlines)
                        if !custom.isEmpty && !options.contains(where: { $0.caseInsensitiveCompare(custom) == .orderedSame }) && !selected.contains(where: { $0.caseInsensitiveCompare(custom) == .orderedSame }) {
                            Button("Add custom: " + custom) { toggle(custom); query = "" }.buttonStyle(.borderless)
                        }
                    }
                }.frame(maxHeight: 240)
                Button("Done") { searching = false; query = "" }.font(.caption).buttonStyle(.borderless)
            }
        }
    }
}

struct CompactRemoveButton: View {
    var label: String
    var action: () -> Void
    var body: some View {
        Button(role: .destructive, action: action) {
            Image(systemName: "xmark").font(.system(size: 13, weight: .medium))
                .foregroundStyle(.secondary).frame(width: 32, height: 32).contentShape(Rectangle())
        }.buttonStyle(.borderless).accessibilityLabel(label)
    }
}

struct OpenItemTextCell: View {
    var label: String
    @Binding var value: String
    var options: [String] = []
    @FocusState private var editing: Bool
    private var matches: [String] {
        let query = (value.components(separatedBy: "\n").last ?? "").lowercased()
        let words = query.split(whereSeparator: { $0.isWhitespace })
        return options.filter { option in words.allSatisfy { option.lowercased().contains(String($0)) } }
    }
    private func choose(_ option: String) {
        var lines = value.components(separatedBy: "\n")
        if !lines.isEmpty { lines.removeLast() }
        if !lines.contains(option) { lines.append(option) }
        lines.append("")
        value = lines.joined(separator: "\n")
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(.caption).fontWeight(.semibold).frame(height: 32, alignment: .bottomLeading)
            ZStack(alignment: .topLeading) {
                if value.isEmpty {
                    Text(options.isEmpty ? label : "Corrective items")
                        .foregroundStyle(.tertiary).padding(.horizontal, 5).padding(.vertical, 8)
                        .allowsHitTesting(false).accessibilityHidden(true)
                }
                TextEditor(text: $value).focused($editing).scrollContentBackground(.hidden)
                    .accessibilityLabel(label)
            }.font(.footnote).frame(height: 44).clipped()
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.secondary.opacity(0.25)))
            if editing && !matches.isEmpty {
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(matches, id: \.self) { option in
                            Button { choose(option) } label: {
                                HStack(alignment: .top) {
                                    Text(option).multilineTextAlignment(.leading).foregroundStyle(.primary)
                                    Spacer(minLength: 4)
                                    if value.components(separatedBy: "\n").contains(option) { Image(systemName: "checkmark").foregroundStyle(.tint) }
                                }.font(.caption).padding(.vertical, 8).contentShape(Rectangle())
                            }.buttonStyle(.plain)
                        }
                    }
                }.frame(maxHeight: 180)
            }
        }.frame(maxWidth: .infinity, alignment: .topLeading)
    }
}

struct ReportEditor: View {
    @Binding var report: ReportDraft
    var reportSelection: Binding<String>? = nil
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
            if let reportSelection {
                Section("Report type") {
                    Picker("Report type", selection: reportSelection) {
                        Text("Shed").tag("SH"); Text("Scaffold").tag("SF"); Text("Other").tag("OT")
                    }.pickerStyle(.segmented)
                }
            }
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
                        Text("Shoring").tag("Shoring")
                        Text("SStab").tag("SStab")
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
            Section("Attendees") {
                ForEach($report.attendees) { $attendee in
                    VStack {
                        HStack { TextField("Name", text: $attendee.name); CompactRemoveButton(label: "Remove attendee") { report.attendees.removeAll { $0.id == attendee.id } } }
                        MultiChoiceField(label: "Company / agency", value: $attendee.company, options: AttendeeOptions.companies)
                        MultiChoiceField(label: "Role", value: $attendee.title, options: AttendeeOptions.roles)
                    }
                }.onDelete { report.attendees.remove(atOffsets: $0) }
                Button("Add attendee") { report.attendees.append(Attendee()) }
                Text("Template names are not proof of attendance. Identify the inspecting PE.").font(.caption)
            }
            if report.equipment != "OT" { Section("Equipment dimensions and details") {
                ForEach(siteFields, id: \.0) { key, label in
                    if key == "tie_type" {
                        siteChoice(label, key: key, options: ["Masonry Anchor", "Concrete Wall Anchor", "Concrete Slab Anchor", "Steel Beam Anchor", "NA"])
                    } else if key == "dunnage_type" {
                        siteChoice(label, key: key, options: ["Grade", "Roof", "Shed", "NA"])
                    } else {
                        TextField(label, text: siteBinding(key))
                    }
                }
                Text("Use NA only when you confirm it is not applicable. Unanswered values stay pending.").font(.caption)
            }
            }
            if report.equipment == "SF" {
                Section("Hoist and chute") {
                    drawingPicker("Hoist inspected?", selection: siteBinding("hoist_inspected"))
                    TextField("Hoist location(s)", text: siteBinding("hoist_locations"))
                    TextField("Height of hoist (ft)", text: siteBinding("hoist_height"))
                    TextField("Hoist model", text: siteBinding("hoist_model"))
                    drawingPicker("Chute inspected?", selection: siteBinding("chute_inspected"))
                    TextField("Chute location(s)", text: siteBinding("chute_locations"))
                    TextField("Height of chute (ft)", text: siteBinding("chute_height"))
                    TextField("Chute model", text: siteBinding("chute_model"))
                }
            }
            Section("Open items") {
                ForEach($report.open_items) { $finding in
                    HStack(alignment: .top, spacing: 10) {
                        OpenItemTextCell(label: "Location / occurrence", value: $finding.location)
                        OpenItemTextCell(label: "Corrective action", value: $finding.action, options: CorrectionOptions.byEquipment[report.equipment] ?? [])
                        CompactRemoveButton(label: "Remove open item") { report.open_items.removeAll { $0.id == finding.id } }.padding(.top, 25)
                    }
                }.onDelete { report.open_items.remove(atOffsets: $0) }
                Button("Add open item") { report.open_items.append(Finding()) }
                Text("Select only actions matching observed deficiencies. Multiple actions stay in this item’s cell; add separate items for different locations. Swipe to remove an item.").font(.caption)
            }
        }.navigationTitle(report.displayName + " facts")
            .scrollDismissesKeyboard(.interactively)
            .toolbar { ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }
            } }
    }
    private func siteChoice(_ label: String, key: String, options: [String]) -> some View {
        MultiChoiceField(label: label, value: siteBinding(key), options: options)
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
