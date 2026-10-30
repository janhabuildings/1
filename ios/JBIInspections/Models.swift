import Foundation

struct Attendee: Codable, Equatable, Identifiable {
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
        inspection.calendar_candidates = self
        if !selectedTitle.isEmpty { inspection.title = selectedTitle }
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
        for index in inspection.reports.indices { fill(&inspection.reports[index], inspection: snapshot, selectedTitle: selectedTitle, previousTitle: previousTitle, applyDates: applyDates) }
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
