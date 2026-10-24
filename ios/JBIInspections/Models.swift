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

struct CalendarCandidates: Decodable { var fields: [String: String]; var equipment: [[String: String]] }

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
