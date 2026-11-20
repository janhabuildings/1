import Foundation

struct Attendee: Codable, Equatable, Identifiable {
    static let defaultEngineerID = "6c7b7cdc-dc93-4b24-9b47-8b12c94b6a67"
    var id = UUID().uuidString
    var name = ""
    var company = ""
    var title = ""
}
struct Finding: Codable, Equatable, Identifiable {
    var id = UUID().uuidString
    var location = ""
    var action = ""
}
struct ReportDraft: Codable, Equatable, Identifiable {
    var id: String { equipment }
    var equipment: String
    var displayName: String { equipment == "SF" ? "Scaffold" : equipment == "SH" ? "Shed" : "Other" }
    var status = ""
    var calendar_title: String?
    var stamp_requested: Bool?
    var client = ""
    var project = ""
    var subject_project = ""
    var request_date = ""
    var inspection_date = ""
    var requested_by = ""
    var permit = ""
    var address = ""
    var locations = ""
    var inspection_code = ""
    var drawings_on_site = ""
    var drawings_approved = ""
    var attendees: [Attendee] = []
    var attendees_override: Bool?
    var site: [String: String] = [:]
    var open_items: [Finding] = []
    var source_references: [String] = []
    var photo_references: [String] = []
}
struct Inspection: Codable, Equatable, Identifiable {
    static func today() -> String {
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }
    var id = UUID().uuidString
    var title = "New inspection"
    var generated_title: String?
    var inspection_number: Int?
    var project = ""
    var inspection_date = Self.today()
    var calendar_text = ""
    var transcript = ""
    var notes = ""
    var reports: [ReportDraft] = []
    // Optional for compatibility with existing phone caches and server records.
    var client: String?
    var request_date: String?
    var requested_by: String?
    var address: String?
    var subject_project: String?
    var calendar_candidates: CalendarCandidates?
    var attendees: [Attendee]?
    var attendees_initialized: Bool?

    var sharedAttendees: [Attendee] {
        get {
            return reports.filter { $0.attendees_override != true }.flatMap(\.attendees).reduce(into: attendees ?? []) { result, person in
                if !result.contains(where: { $0.id == person.id || ($0.name == person.name && $0.company == person.company && $0.title == person.title) }) { result.append(person) }
            }
        }
        set {
            attendees_initialized = true
            attendees = newValue
            for index in reports.indices where reports[index].attendees_override != true { reports[index].attendees = newValue }
        }
    }
    mutating func prepareAttendees(previousClient: String? = nil) {
        var people = sharedAttendees
        if attendees_initialized != true && people.isEmpty {
            people = [Attendee(company: client ?? "", title: "Competent Person/Site Supervisor"),
                      Attendee(company: "NYC SCA", title: "Safety Inspector"),
                      Attendee(id: Attendee.defaultEngineerID, name: "Kamruz Zaman", company: "DSENY Engineering Services PC", title: "PE")]
        }
        if let first = people.first, first.title == "Competent Person/Site Supervisor",
           first.company.isEmpty || (previousClient != nil && first.company == previousClient), let client, !client.isEmpty {
            people[0].company = client
        }
        if let index = people.firstIndex(where: { $0.id == Attendee.defaultEngineerID || ($0.name == "Kamruz Zaman" && $0.company == "DSENY Engineering Services PC" && $0.title == "PE") }) {
            let engineer = people.remove(at: index); people.append(engineer)
        }
        sharedAttendees = people
    }
    mutating func insertAttendee(_ person: Attendee) {
        var people = sharedAttendees
        let last = people.last
        let index = people.firstIndex(where: { $0.id == Attendee.defaultEngineerID }) ?? (last?.company == "DSENY Engineering Services PC" && last?.title == "PE" ? max(0, people.count - 1) : people.count)
        people.insert(person, at: index); sharedAttendees = people
    }
    // Called only for a user's title selection, never merely parsing a template.
    mutating func confirmCalendarTitle(_ title: String, candidates: CalendarCandidates?) {
        guard let row = candidates?.report_subjects?.first(where: { $0["title"] == title }),
              let index = reports.firstIndex(where: { $0.equipment == row["equipment"] }) else { return }
        let previous = reports[index].calendar_title ?? ""
        if let candidates { let snapshot = self; candidates.fill(&reports[index], inspection: snapshot, selectedTitle: title, previousTitle: previous) }
        reports[index].calendar_title = title
        if title.range(of: #"-\s*(?:No\s+OIs|PE\s+CERT\s+OF\s+USE)\s*$"#, options: [.regularExpression, .caseInsensitive]) != nil { reports[index].status = "No OIs" }
        else if title.range(of: #"-\s*OIs\s*$"#, options: [.regularExpression, .caseInsensitive]) != nil { reports[index].status = "OIs"; reports[index].stamp_requested = false }
    }
}
extension Inspection {
    static func equipmentCode(_ name: String) -> String {
        let value = name.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression).trimmingCharacters(in: .whitespacesAndNewlines)
        switch value.lowercased() {
        case "sh", "sidewalk shed": return "SH"
        case "sf", "supported scaffold": return "SF"
        case "soe", "support of excavation": return "SOE"
        case "sstab", "structural stability": return "SStab"
        case "fp", "fall protection": return "FP"
        default: return value
        }
    }
    var equipmentTitleKey: String {
        reports.map { $0.equipment + ":" + ($0.site["other_name"] ?? "") + ":" + ($0.site["report_type"] ?? "") }.joined(separator: "|")
    }
    mutating func refreshTitle(force: Bool = false) {
        if !force && !title.isEmpty && title != "New inspection", let generated_title, title != generated_title { return }
        let candidates = calendar_candidates
        var labels = candidates?.equipment_labels ?? []
        if labels.isEmpty {
            labels = (candidates?.report_subjects ?? candidates?.equipment ?? []).map { row in
                let kind = row["equipment"] ?? ""
                return Self.equipmentCode(["SF", "SH"].contains(kind) ? kind : row["other_name"] ?? row["report_type"] ?? "Other")
            }
        }
        for report in reports {
            if report.equipment != "OT" { labels.append(report.equipment); continue }
            let name = report.site["other_name"] ?? ""
            let type = report.site["report_type"] ?? ""
            if !name.isEmpty { labels.append(Self.equipmentCode(name)) }
            else if !type.isEmpty && type != "Unknown / custom" { labels.append(Self.equipmentCode(type)) }
            else if !(candidates?.equipment.contains(where: { $0["equipment"] == "OT" }) ?? false) { labels.append("Other") }
        }
        labels = labels.reduce(into: []) { result, item in if !item.isEmpty && !result.contains(where: { $0.caseInsensitiveCompare(item) == .orderedSame }) { result.append(item) } }
        var parts = [client ?? "", project].map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        if !labels.isEmpty { parts.append(labels.joined(separator: " ")) }
        if !parts.isEmpty { title = inspection_date + " " + parts.joined(separator: "-") }
        else if force || title == "New inspection" || title == generated_title { title = inspection_date + " Inspection " + String(inspection_number ?? 1) }
        generated_title = title
    }
    static func fresh(existing: [Inspection], on date: String = Inspection.today()) -> Inspection {
        let sameDay = existing.filter { $0.inspection_date == date }
        let number = max(sameDay.count, sameDay.compactMap(\.inspection_number).max() ?? 0) + 1
        var value = Inspection(); value.inspection_date = date; value.inspection_number = number
        value.refreshTitle(force: true); return value
    }
}

struct LocalMedia: Codable, Equatable, Identifiable {
    var id = UUID().uuidString
    var inspectionID: String
    var kind: String
    var relativePath: String
    var note = ""
    var equipment = ""
    var uploaded = false
    var mime: String
}
struct Artifact: Codable, Equatable, Identifiable {
    var generation_id: String?
    var id: String
    var filename: String
    var mime: String
    var equipment: String
}
struct ExportResult: Decodable {
    var artifacts: [Artifact]
    var reports: [[String: JSONValue]]
    var notice: String
}
// Preserve API diagnostics and suggestions without treating them as approved report facts.
enum JSONValue: Codable {
    case string(String), number(Double), bool(Bool), array([JSONValue]), object([String: JSONValue]), null
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode([JSONValue].self) { self = .array(v) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .object(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }
}
struct Cache: Codable {
    var inspections: [Inspection] = []
    var media: [LocalMedia] = []
    var dirty: Set<String> = []
    var pendingInspectionDeletions: Set<String>?
    var pendingMediaDeletions: Set<String>?
    var artifactOwners: [String: String]?
    var savedRows: [SavedRow]?
    var pendingSavedRows: Set<String>?
}

struct SuggestedFinding: Decodable, Identifiable {
    var id: String { equipment + observation + location }
    var equipment: String
    var observation: String
    var location: String
    var suggested_action: String
    var source_quote: String
    var photo_id: String?
    var references: [SuggestedCitation]
    var uncertainties: [String]?
}
struct AISuggestionSet: Decodable {
    var suggested_findings: [SuggestedFinding]
    var missing_information: [String]
    var warnings: [String]
}
struct AISuggestionResponse: Decodable { var suggestions: AISuggestionSet }

struct CalendarCandidates: Codable, Equatable {
    var fields: [String: String]
    var equipment: [[String: String]]
    var titles: [String]?
    var report_subjects: [[String: String]]?
    var equipment_labels: [String]?

    static func missing(_ value: String?) -> Bool {
        ["", "[pending confirmation]", "pending", "tbd"].contains((value ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
    }

    func fill(_ report: inout ReportDraft, inspection: Inspection, selectedTitle: String = "", previousTitle: String = "", applyDates: Bool = false) {
        if Self.missing(report.client) { report.client = inspection.client ?? fields["client"] ?? "" }
        if Self.missing(report.project) { report.project = inspection.project }
        if Self.missing(report.requested_by) { report.requested_by = inspection.requested_by ?? fields["requested_by"] ?? "" }
        if Self.missing(report.address) { report.address = inspection.address ?? fields["address"] ?? "" }
        if Self.missing(report.request_date) || applyDates { report.request_date = inspection.request_date ?? fields["request_date"] ?? report.request_date }
        if Self.missing(report.inspection_date) || applyDates { report.inspection_date = inspection.inspection_date }
        if Self.missing(report.drawings_on_site) { report.drawings_on_site = fields["drawings_on_site"] ?? "" }
        if Self.missing(report.drawings_approved) { report.drawings_approved = fields["drawings_approved"] ?? "" }
        let selected = report_subjects?.first { $0["title"] == selectedTitle && $0["equipment"] == report.equipment }
        let previous = report_subjects?.first { $0["title"] == previousTitle && $0["equipment"] == report.equipment }
        let candidate = selected ?? equipment.first { $0["equipment"] == report.equipment } ?? [:]
        if let value = candidate["permit"], Self.missing(report.permit) { report.permit = value }
        if inspection.reports.count <= 1 && (equipment.isEmpty || equipment.contains(where: { $0["equipment"] == report.equipment })), Self.missing(report.permit) { report.permit = fields["permit"] ?? "" }
        if let value = candidate["inspection_code"], Self.missing(report.inspection_code) || (previous?["inspection_code"] != nil && report.inspection_code == previous?["inspection_code"]) { report.inspection_code = value }
        if let value = candidate["subject_project"], Self.missing(report.subject_project) || (previous?["subject_project"] != nil && report.subject_project == previous?["subject_project"]) { report.subject_project = value }
        for key in ["report_type", "other_name"] {
            if let value = candidate[key], Self.missing(report.site[key]) || (previous?[key] != nil && report.site[key] == previous?[key]) { report.site[key] = value }
        }
    }

    func apply(to inspection: inout Inspection, selectedTitle: String = "", previousTitle: String = "", applyDates: Bool = false) {
        let previousClient = inspection.client
        inspection.calendar_candidates = self
        if Self.missing(inspection.project) { inspection.project = fields["project"] ?? "" }
        if let value = fields["inspection_date"], applyDates || Self.missing(inspection.inspection_date) { inspection.inspection_date = value }
        if Self.missing(inspection.client) { inspection.client = fields["client"] }
        if Self.missing(inspection.request_date) || applyDates { inspection.request_date = fields["request_date"] ?? inspection.request_date }
        if Self.missing(inspection.requested_by) { inspection.requested_by = fields["requested_by"] }
        if Self.missing(inspection.address) { inspection.address = fields["address"] }
        for item in equipment {
            if let kind = item["equipment"], ["SF", "SH", "OT"].contains(kind), !inspection.reports.contains(where: { $0.equipment == kind }) { inspection.reports.append(ReportDraft(equipment: kind)) }
        }
        let snapshot = inspection
        for index in inspection.reports.indices { fill(&inspection.reports[index], inspection: snapshot, selectedTitle: inspection.reports[index].calendar_title ?? "", applyDates: applyDates) }
        inspection.prepareAttendees(previousClient: previousClient)
        inspection.refreshTitle(force: true)
    }
}

struct SuggestedCitation: Decodable, Identifiable {
    var id: String { reference_id + quote }
    var reference_id: String
    var quote: String
    var url: String?
    var agency: String
    var section: String
    var verified: Bool?
    var source_pages: [Int]?
    var document: String?
}

struct DeletionState: Decodable { var inspections: [String]; var media: [String] }
struct StampAsset: Decodable { var id: String; var owner: String; var sha256: String }

struct SavedRow: Codable, Sendable, Equatable, Identifiable {
    var id = UUID().uuidString
    var kind: String
    var equipment = ""
    var name = ""
    var company = ""
    var title = ""
    var location = ""
    var action = ""
    var summary: String { (kind == "company" ? [company] : kind == "attendee" ? [name, company, title] : [equipment, location, action]).filter { !$0.isEmpty }.joined(separator: " · ") }
    func value(_ key: String) -> String {
        switch key { case "name": return name; case "company": return company; case "title": return title; case "location": return location; default: return action }
    }
}
struct DraftPerson: Codable, Sendable, Identifiable {
    var saved_matches: [SavedRow] = []
    var matched_saved_id: String?
    var id: String
    var name: String
    var company: String
    var title: String
    var source_quote: String
}
struct DraftOpenItem: Codable, Sendable, Identifiable {
    var saved_matches: [SavedRow] = []
    var matched_saved_id: String?
    var id: String
    var equipment: String
    var location: String
    var action: String
    var source_quote: String
}
struct DraftFact: Codable, Sendable, Identifiable {
    var id: String { field }
    var field: String
    var value: String
    var source_quote: String
}
struct TranscriptDraft: Codable, Sendable {
    var attendees: [DraftPerson] = []
    var open_items: [DraftOpenItem] = []
    var facts: [DraftFact] = []
    var warnings: [String] = []
}
struct TranscriptDraftResponse: Decodable { var draft: TranscriptDraft }

extension Inspection {
    mutating func applyTranscriptDraft(_ draft: TranscriptDraft) {
        for fact in draft.facts where !fact.value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            switch fact.field {
            case "project": if project.isEmpty { project = String(fact.value.prefix(200)) }
            case "client": if (client ?? "").isEmpty { client = fact.value }
            case "address": if (address ?? "").isEmpty { address = fact.value }
            case "requested_by": if (requested_by ?? "").isEmpty { requested_by = fact.value }
            case "request_date": if (request_date ?? "").isEmpty { request_date = fact.value }
            // The existing inspection date is intentionally preserved.
            default: break
            }
        }
        for person in draft.attendees where ![person.name,person.company,person.title].allSatisfy({ $0.isEmpty }) {
            var people = sharedAttendees
            let index = people.firstIndex { row in
                (!person.name.isEmpty && row.name.localizedCaseInsensitiveCompare(person.name) == .orderedSame) ||
                (row.name.isEmpty && !person.company.isEmpty && row.company == person.company && row.title == person.title)
            }
            if let index {
                if people[index].name.isEmpty { people[index].name = person.name }
                if people[index].company.isEmpty { people[index].company = person.company }
                if people[index].title.isEmpty { people[index].title = person.title }
                sharedAttendees = people
            } else { insertAttendee(Attendee(name: person.name, company: person.company, title: person.title)) }
        }
        for item in draft.open_items where ["SF","SH","OT"].contains(item.equipment) && (!item.location.isEmpty || !item.action.isEmpty) {
            if !reports.contains(where: { $0.equipment == item.equipment }) {
                var report = ReportDraft(equipment: item.equipment)
                report.project = project; report.inspection_date = inspection_date; report.attendees = sharedAttendees
                report.client = client ?? ""; report.address = address ?? ""; report.request_date = request_date ?? ""
                report.requested_by = requested_by ?? ""; report.subject_project = subject_project ?? ""
                calendar_candidates?.fill(&report, inspection: self, selectedTitle: "")
                reports.append(report)
            }
            if let index = reports.firstIndex(where: { $0.equipment == item.equipment }) {
                if !reports[index].open_items.contains(where: { $0.location == item.location && $0.action == item.action }) {
                    reports[index].open_items.append(Finding(location: item.location, action: item.action))
                }
                reports[index].status = "OIs"; reports[index].calendar_title = ""; reports[index].stamp_requested = false
            }
        }
        refreshTitle(force: true)
    }
}

// Pure, offline extraction of explicitly labeled transcript fields.
enum CodedTranscript {
    static let labels = ["attendee":"name", "attendees":"name", "name":"name", "company":"company", "company name":"company", "agency":"company", "company / agency":"company", "role":"title", "title":"title", "equipment":"equipment", "product":"equipment", "location":"location", "occurrence":"location", "corrective action":"action", "action":"action", "open item":"open_item", "observation":"observation", "client":"client", "project":"project", "address":"address", "requested by":"requested_by", "request date":"request_date", "inspection date":"inspection_date", "inspected on":"inspection_date"]
    static let limits = ["name":300, "company":300, "title":300, "location":3000, "action":5000, "project":200, "client":1000, "address":2000, "requested_by":1000, "request_date":10, "inspection_date":10]
    static let negated = #"(?:^\s*no\b)|\b(?:no open items?|no deficiencies|not required|no need|do not|already (?:fixed|repaired|corrected|completed)|(?:has|have) been (?:fixed|repaired|corrected))\b"#
    static func matches(_ pattern: String, _ value: String) -> [NSTextCheckingResult] {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return [] }
        return regex.matches(in: value, range: NSRange(location: 0, length: (value as NSString).length))
    }
    static func normalized(_ value: String) -> String {
        let source = value.lowercased() as NSString
        return matches(#"\w+"#, source as String).map { source.substring(with: $0.range) }.joined(separator: " ")
    }
    static func similarity(_ left: String, _ right: String) -> Double {
        let a = Array(normalized(left).prefix(400)), b = Array(normalized(right).prefix(400))
        guard !a.isEmpty && !b.isEmpty else { return 0 }
        if a == b { return 1 }
        var previous = Array(0...b.count)
        for (i, x) in a.enumerated() {
            var current = [i + 1]
            for (j, y) in b.enumerated() { current.append(min(current[j] + 1, previous[j + 1] + 1, previous[j] + (x == y ? 0 : 1))) }
            previous = current
        }
        return 1 - Double(previous[b.count]) / Double(max(a.count, b.count))
    }
    static func ranked(_ values: [String:String], equipment: String, kind: String, library: [SavedRow]) -> [(Double,SavedRow)] {
        let keys = kind == "attendee" ? ["name"] : ["action", "location"]
        return library.filter { $0.kind == kind && (kind == "attendee" || equipment == "unknown" || $0.equipment.isEmpty || $0.equipment == equipment) }.compactMap { saved -> (Double, SavedRow)? in
            let score = keys.filter { normalized(values[$0] ?? "").count >= 3 }.map { similarity(values[$0] ?? "", saved.value($0)) }.max() ?? 0
            return score >= 0.64 ? (score,saved) : nil
        }.sorted { $0.0 > $1.0 }
    }
    static func equipmentCode(_ value: String) -> String {
        let text = normalized(value)
        if ["sf","scaffold","supported scaffold"].contains(text) { return "SF" }
        if ["sh","shed","sidewalk shed"].contains(text) { return "SH" }
        if ["ot","other","soe","support of excavation","shoring","sstab","structural stability","fp","fall protection","fence","structural netting","structural netting as ohp"].contains(text) { return "OT" }
        return "unknown"
    }
    static func extract(_ text: String, library: [SavedRow]) -> TranscriptDraft {
        var draft = TranscriptDraft(warnings: ["Coded extraction only; no AI service was used. Review every value before applying."])
        let source = text as NSString
        let label = labels.keys.sorted { $0.count > $1.count }.map { NSRegularExpression.escapedPattern(for: $0) }.joined(separator: "|")
        let split = #"[\r\n]+|(?<=[.;!?])\s+(?=(?:"# + label + #")\b)|;\s*(?=(?:"# + label + #")\b)|,\s*(?=(?:"# + label + #")\s*(?::|\s))"#
        let field = #"^\s*("# + label + #")\b\s*(?::|=|\s+-\s+)?\s*(.+?)\s*$"#
        var person: [String:String] = [:], item: [String:String] = [:]
        var personStart = 0, personEnd = 0, itemStart = 0, itemEnd = 0
        var equipment = "unknown"
        var unrecognizedEquipment = false
        var equipmentStart: Int? = nil
        var seenFacts: Set<String> = []
        func warn(_ message: String) { if !draft.warnings.contains(message) && draft.warnings.count < 30 { draft.warnings.append(message) } }
        func flushPerson() {
            defer { person = [:] }
            guard person.values.contains(where: { !$0.isEmpty }), draft.attendees.count < 50 else { return }
            let quote = source.substring(with: NSRange(location: personStart, length: personEnd - personStart)).trimmingCharacters(in: .whitespacesAndNewlines)
            guard quote.count <= 5000, matches(#"\b(?:absent|not present|not attending|did not attend|not an attendee|not on site|not here)\b"#, quote).isEmpty, matches(#"^(?:not|no)\b"#, person["name"] ?? "").isEmpty else { return }
            var row = DraftPerson(id: UUID().uuidString, name: person["name"] ?? "", company: person["company"] ?? "", title: person["title"] ?? "", source_quote: quote)
            let ranked = Self.ranked(person, equipment: "unknown", kind: "attendee", library: library)
            row.saved_matches = Array(ranked.prefix(5).map { $0.1 })
            let exact = ranked.filter { $0.0 == 1 }
            if exact.count == 1 {
                let saved = exact[0].1; row.matched_saved_id = saved.id
                if row.name.isEmpty { row.name = saved.name }
                if row.company.isEmpty { row.company = saved.company }
                if row.title.isEmpty { row.title = saved.title }
            }
            draft.attendees.append(row)
        }
        func flushItem() {
            defer { item = [:]; equipmentStart = nil }
            guard !(item["location"] ?? "").isEmpty || !(item["action"] ?? "").isEmpty, draft.open_items.count < 100 else { return }
            let quote = source.substring(with: NSRange(location: itemStart, length: itemEnd - itemStart)).trimmingCharacters(in: .whitespacesAndNewlines)
            guard quote.count <= 5000 else { return }
            guard matches(negated, quote).isEmpty else { warn("A negated or already-corrected item was not added; review its wording manually."); return }
            var row = DraftOpenItem(id: UUID().uuidString, equipment: item["equipment"] ?? "unknown", location: item["location"] ?? "", action: item["action"] ?? "", source_quote: quote)
            let ranked = Self.ranked(item, equipment: row.equipment, kind: "open_item", library: library)
            row.saved_matches = Array(ranked.prefix(5).map { $0.1 })
            let exact = ranked.filter { $0.0 == 1 }
            if exact.count == 1 && item["unrecognized_equipment"] != "true" {
                let saved = exact[0].1; row.matched_saved_id = saved.id
                if row.location.isEmpty { row.location = saved.location }
                if row.action.isEmpty { row.action = saved.action }
                if row.equipment == "unknown" && !saved.equipment.isEmpty { row.equipment = saved.equipment }
            }
            draft.open_items.append(row)
            if row.action.isEmpty { warn("A location has no explicit corrective action. Fill it or remove the item before applying.") }
        }
        let cuts = matches(split, text).map { ($0.range.location, NSMaxRange($0.range)) } + [(source.length,source.length)]
        var start = 0
        for (end, next) in cuts {
            let chunkStart = start, chunk = source.substring(with: NSRange(location: start, length: end - start)); start = next
            guard let match = matches(field, chunk).first else { continue }
            let part = chunk as NSString
            guard let key = labels[part.substring(with: match.range(at: 1)).lowercased()] else { continue }
            let value = part.substring(with: match.range(at: 2)).trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: ".!?")).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !value.isEmpty else { continue }
            if let limit = limits[key], value.count > limit { warn("A value exceeded its cell limit and was left for manual entry."); continue }
            if ["name","company","title"].contains(key) {
                flushItem()
                if person[key] != nil { flushPerson() }
                if person.isEmpty { personStart = chunkStart }
                person[key] = value; personEnd = end
            } else if key == "equipment" {
                flushPerson(); flushItem(); equipment = equipmentCode(value); equipmentStart = chunkStart; unrecognizedEquipment = equipment == "unknown"
                if equipment == "unknown" { warn("Equipment was not recognized. Assign the report type before applying.") }
            } else if ["location","action","open_item","observation"].contains(key) {
                flushPerson()
                if key == "observation" { warn("Observations are not automatically converted into corrective actions."); continue }
                if !matches(negated, value).isEmpty { item = [:]; equipmentStart = nil; warn("A negated or already-corrected item was not added; review its wording manually."); continue }
                let target = key == "open_item" ? "action" : key
                if !(item[target] ?? "").isEmpty || (target == "location" && !(item["action"] ?? "").isEmpty) { flushItem() }
                if item.isEmpty { itemStart = equipmentStart ?? chunkStart; item["equipment"] = equipment; item["unrecognized_equipment"] = unrecognizedEquipment ? "true" : "false" }
                item[target] = value; itemEnd = end
                if key == "open_item" { warn("Confirm that the open-item wording describes the corrective action you want in the report.") }
            } else {
                flushPerson(); flushItem()
                if seenFacts.contains(key) { warn("Repeated common facts were left for review; only the first labeled value is proposed."); continue }
                if key.hasSuffix("_date") {
                    let formatter = DateFormatter(); formatter.calendar = Calendar(identifier: .gregorian); formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.dateFormat = "yyyy-MM-dd"; formatter.isLenient = false
                    guard !matches(#"^\d{4}-\d{2}-\d{2}$"#, value).isEmpty, let date = formatter.date(from: value), formatter.string(from: date) == value else { warn("Use YYYY-MM-DD for coded date extraction."); continue }
                }
                seenFacts.insert(key); draft.facts.append(DraftFact(field: key, value: value, source_quote: chunk.trimmingCharacters(in: .whitespacesAndNewlines)))
            }
        }
        flushPerson(); flushItem()
        if draft.attendees.isEmpty && draft.open_items.isEmpty && draft.facts.isEmpty { warn("No labeled values found. Try: Attendee: John Smith. Company: ABC. Role: Site Supervisor. Equipment: Scaffold. Location: North. Action: Install missing pins. Or choose optional AI for unstructured notes.") }
        return draft
    }
}
