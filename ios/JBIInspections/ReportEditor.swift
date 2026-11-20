import SwiftUI

enum AttendeeOptions {
    static let roles = ["Competent Person/Site Supervisor", "Safety Inspector", "Competent Person/ Equipment Installation Supervisor", "Competent Person", "GC’s Project Manager", "CM’s Representative", "Owner’s Representative", "PE"]
    static let companies = ["NYC SCA", "DSENY Engineering Services PC"]
}

struct AttendeeListFields: View {
    @EnvironmentObject var store: InspectionStore
    @FocusState private var nameFocus: String?
    private var attendeeRows: [SavedRow] { (store.cache.savedRows ?? []).filter { $0.kind == "attendee" } }
    private func fill(_ row: SavedRow, person: Binding<Attendee>) {
        if !row.name.isEmpty { person.wrappedValue.name = row.name }
        if !row.company.isEmpty { person.wrappedValue.company = row.company }
        if !row.title.isEmpty { person.wrappedValue.title = row.title }
    }
    @Binding var attendees: [Attendee]
    var client: String
    var body: some View {
        ForEach($attendees) { $person in
            VStack(alignment: .leading) {
                HStack {
                    TextField("Name", text: $person.name).focused($nameFocus, equals: person.id)
                    CompactRemoveButton(label: "Remove attendee") { attendees.removeAll { $0.id == person.id } }
                }
                if nameFocus == person.id {
                    SavedRowMatches(query: person.name, key: "name", rows: attendeeRows) { row in fill(row, person: $person); nameFocus = nil }
                }
                MultiChoiceField(label: "Company / agency", value: $person.company, options: Array(Set(AttendeeOptions.companies + store.companyNames + [client].filter { !$0.isEmpty })).sorted(), rowOptions: attendeeRows, rowKey: "company", chooseRow: { fill($0, person: $person) })
                MultiChoiceField(label: "Role", value: $person.title, options: AttendeeOptions.roles, rowOptions: attendeeRows, rowKey: "title", chooseRow: { fill($0, person: $person) })
                HStack {
                    Button("Save attendee row") { store.saveSuggestion(SavedRow(kind: "attendee", name: person.name, company: person.company, title: person.title)) }
                    Button("Save company name") { store.saveCompanyNames(person.company) }.disabled(person.company.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }.font(.caption).buttonStyle(.borderless)
            }
        }
        Button("Add attendee") {
            let anchor = attendees.firstIndex(where: { $0.id == Attendee.defaultEngineerID })
            let last = attendees.last
            let index = anchor ?? (last?.company == "DSENY Engineering Services PC" && last?.title == "PE" ? max(0, attendees.count - 1) : attendees.count)
            attendees.insert(Attendee(), at: index)
        }
    }
}

struct ReportFactsEditor: View {
    @Binding var inspection: Inspection
    var candidates: CalendarCandidates?
    @State private var selectedEquipment: String
    init(inspection: Binding<Inspection>, candidates: CalendarCandidates?, initialEquipment: String) {
        _inspection = inspection; self.candidates = candidates
        _selectedEquipment = State(initialValue: initialEquipment)
    }
    private var selection: Binding<String> {
        Binding(get: { selectedEquipment }, set: { equipment in
            UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
            if !inspection.reports.contains(where: { $0.equipment == equipment }), let index = inspection.reports.firstIndex(where: { $0.equipment == selectedEquipment }) {
                inspection.reports[index].equipment = equipment
                inspection.reports[index].calendar_title = nil
                inspection.reports[index].stamp_requested = false
                inspection.refreshTitle(force: true)
            }
            selectedEquipment = equipment
        })
    }
    var body: some View {
        let equipment = selectedEquipment
        let subjects = candidates?.report_subjects ?? []
        let titles = subjects.filter { $0["equipment"] == equipment }.compactMap { $0["title"] }
        ReportEditor(report: Binding(get: { inspection.reports.first(where: { $0.equipment == equipment }) ?? ReportDraft(equipment: equipment) }, set: { value in
            if let index = inspection.reports.firstIndex(where: { $0.equipment == equipment }) { inspection.reports[index] = value }
        }), reportSelection: selection, calendarTitles: titles, chooseCalendarTitle: { title in
            if title.isEmpty {
                if let index = inspection.reports.firstIndex(where: { $0.equipment == equipment }) { inspection.reports[index].calendar_title = nil }
            } else { inspection.confirmCalendarTitle(title, candidates: candidates) }
        }, inspectionAttendees: inspection.sharedAttendees, attendeeClient: inspection.client ?? "").id(equipment)
    }
}

struct MultiChoiceField: View {
    var label: String
    @Binding var value: String
    var options: [String]
    var separator = "; "
    var rowOptions: [SavedRow] = []
    var rowKey = ""
    var chooseRow: ((SavedRow) -> Void)?
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
                        SavedRowMatches(query: query, key: rowKey, rows: rowOptions) { row in
                            chooseRow?(row); query = ""; searching = false
                        }
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
    var rowOptions: [SavedRow] = []
    var rowKey = ""
    var chooseRow: ((SavedRow) -> Void)?
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
            if editing {
                SavedRowMatches(query: value, key: rowKey, rows: rowOptions) { row in chooseRow?(row); editing = false }
            }
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
    @EnvironmentObject var store: InspectionStore
    private var itemRows: [SavedRow] { (store.cache.savedRows ?? []).filter { $0.kind == "open_item" && ($0.equipment.isEmpty || $0.equipment == report.equipment) } }
    private func fill(_ row: SavedRow, finding: Binding<Finding>) {
        if !row.location.isEmpty { finding.wrappedValue.location = row.location }
        if !row.action.isEmpty { finding.wrappedValue.action = row.action }
    }
    @Binding var report: ReportDraft
    var reportSelection: Binding<String>? = nil
    var calendarTitles: [String]
    var chooseCalendarTitle: (String) -> Void
    var inspectionAttendees: [Attendee]
    var attendeeClient: String
    @State private var attendeesExpanded = false
    @State private var attendeeNotice = ""
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
            Section("Inspection title from calendar") {
                if !calendarTitles.isEmpty {
                    Picker("Report subject", selection: Binding(get: { report.calendar_title ?? "" }, set: chooseCalendarTitle)) {
                        Text("Choose a title…").tag("")
                        ForEach(calendarTitles, id: \.self) { Text($0).tag($0) }
                    }
                    Button("Use selected title and outcome") { chooseCalendarTitle(report.calendar_title ?? "") }.disabled((report.calendar_title ?? "").isEmpty)
                } else { Text("Extract calendar content on the inspection page to see matching subjects.").font(.caption).foregroundStyle(.secondary) }
                if !report.status.isEmpty { Text(report.status == "No OIs" ? "Outcome: No open items" : "Outcome: Open items").font(.caption).foregroundStyle(.secondary) }
            }
            Section {
                DisclosureGroup("Outcome for custom titles") {
                    Picker("Result — explicit confirmation", selection: Binding(get: { report.status }, set: { value in report.calendar_title = nil; report.status = value; if value != "No OIs" { report.stamp_requested = false } })) {
                        Text("Not confirmed").tag("")
                        Text("Open items").tag("OIs")
                        Text("No open items").tag("No OIs")
                    }
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
            Section {
                DisclosureGroup("Attendees (\(report.attendees.count))", isExpanded: $attendeesExpanded) {
                    Text(report.attendees_override == true ? "Edited for this report only. Reset to use the current inspection list." : "Filled from the inspection. Editing creates a list for this report only.").font(.caption).foregroundStyle(.secondary)
                    AttendeeListFields(attendees: Binding(get: { report.attendees }, set: { value in report.attendees = value; report.attendees_override = true }), client: attendeeClient)
                    Button("Reset to inspection attendees") {
                        report.attendees = inspectionAttendees; report.attendees_override = false
                        attendeeNotice = "Attendees reset to the inspection list."
                    }
                    if !attendeeNotice.isEmpty { Text(attendeeNotice).font(.caption).foregroundStyle(.secondary) }
                }
            }
            Section("Drawing status") {
                drawingPicker("PE drawings on site", selection: $report.drawings_on_site)
                drawingPicker("DOB / SCA approved", selection: $report.drawings_approved)
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
            if report.status == "OIs" { Section("Open items") {
                ForEach($report.open_items) { $finding in
                    HStack(alignment: .top, spacing: 10) {
                        OpenItemTextCell(label: "Location / occurrence", value: $finding.location, rowOptions: itemRows, rowKey: "location", chooseRow: { fill($0, finding: $finding) })
                        OpenItemTextCell(label: "Corrective action", value: $finding.action, options: CorrectionOptions.byEquipment[report.equipment] ?? [], rowOptions: itemRows, rowKey: "action", chooseRow: { fill($0, finding: $finding) })
                        CompactRemoveButton(label: "Remove open item") { report.open_items.removeAll { $0.id == finding.id } }.padding(.top, 25)
                    }
                    Button("Save open-item row for reuse") { store.saveSuggestion(SavedRow(kind: "open_item", equipment: report.equipment, location: finding.location, action: finding.action)) }.font(.caption).buttonStyle(.borderless)
                }.onDelete { report.open_items.remove(atOffsets: $0) }
                Button("Add open item") { report.open_items.append(Finding()) }
                Text("Select only actions matching observed deficiencies. Multiple actions stay in this item’s cell; add separate items for different locations. Swipe to remove an item.").font(.caption)
            }
            }
            if report.status == "No OIs" {
                Section("Signature / stamp") {
                    Toggle("Apply saved signature/stamp to this report", isOn: Binding(get: { report.stamp_requested ?? false }, set: { report.stamp_requested = $0 }))
                }
            }
        }.onChange(of: report.status) { _, value in if value != "No OIs" { report.stamp_requested = false } }
        .navigationTitle(report.displayName + " facts")
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

struct SavedRowMatches: View {
    var query: String
    var key: String
    var rows: [SavedRow]
    var choose: (SavedRow) -> Void
    var body: some View {
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.count >= 2 {
            ForEach(Array(rows.filter { $0.value(key).localizedCaseInsensitiveContains(text) }.prefix(5))) { row in
                Button { choose(row) } label: { Label((row.kind == "attendee" && key == "company" ? "Fill attendee row: " : "") + row.summary, systemImage: "text.badge.checkmark").font(.caption) }.buttonStyle(.borderless)
            }
        }
    }
}
struct SavedRowLibrary: View {
    @EnvironmentObject var store: InspectionStore
    @State private var query = ""
    @State private var newCompany = ""
    private var matches: [SavedRow] { (store.cache.savedRows ?? []).filter { query.isEmpty || $0.summary.localizedCaseInsensitiveContains(query) } }
    private func savedEntry(_ row: SavedRow) -> some View {
        VStack(alignment: .leading) {
            Text(row.summary)
            Text(store.cache.pendingSavedRows?.contains(row.id) == true ? "Saved on this phone · sync pending" : "Saved suggestion").font(.caption).foregroundStyle(.secondary)
            Button(row.kind == "company" ? "Delete saved company" : "Delete saved suggestion", role: .destructive) { Task { do { try await store.deleteSuggestion(row) } catch { store.error = error.localizedDescription } } }
        }
    }
    var body: some View {
        List {
            Text("Save rows while drafting. Selecting a saved suggestion fills its nonempty cells; every value stays editable. Synced rows are shared across web and iPhone.").font(.caption)
            Button("Import from saved reports") {
                Task {
                    do {
                        _ = try await store.api.request("/saved-rows/import-history", method: "POST")
                        try await store.syncSuggestions()
                        store.libraryNotice = "Saved report rows imported. Duplicates were skipped."
                    } catch { store.error = error.localizedDescription }
                }
            }.disabled(!store.connected)
            if !store.libraryNotice.isEmpty { Text(store.libraryNotice).font(.caption) }
            Section("Company names · company cell only") {
                TextField("New company name", text: $newCompany)
                Button("Save company name") { store.saveCompanyNames(newCompany); newCompany = "" }.disabled(newCompany.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                ForEach(matches.filter { $0.kind == "company" }) { row in savedEntry(row) }
            }
            Section("Saved attendee and open-item rows · linked cells") {
                ForEach(matches.filter { $0.kind != "company" }) { row in savedEntry(row) }
            }
        }.searchable(text: $query).navigationTitle("Saved rows")
        .task { do { try await store.syncSuggestions() } catch { store.error = error.localizedDescription } }
    }
}
