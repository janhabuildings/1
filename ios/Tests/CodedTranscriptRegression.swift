import Foundation

@main struct CodedTranscriptRegression {
    static func main() throws {
        let data = try Data(contentsOf: URL(fileURLWithPath: "ios/Tests/coded-transcript-cases.json"))
        let cases = try JSONSerialization.jsonObject(with: data) as! [[String:Any]]
        for fixture in cases {
            let name = fixture["name"] as! String, text = fixture["text"] as! String
            let library = try JSONDecoder().decode([SavedRow].self, from: JSONSerialization.data(withJSONObject: fixture["library"]!))
            let draft = CodedTranscript.extract(text, library: library)
            let result = try JSONSerialization.jsonObject(with: JSONEncoder().encode(draft)) as! [String:Any]
            for section in ["attendees","open_items","facts"] {
                let actual = result[section] as! [[String:Any]], expected = fixture[section] as! [[String:Any]]
                precondition(actual.count == expected.count, "\(name) \(section): expected \(expected.count), got \(actual)")
                for (row, desired) in zip(actual,expected) {
                    precondition(text.contains(row["source_quote"] as! String), "Source quotation not found: \(name)")
                    for (key,value) in desired {
                        if key == "saved_match_ids" {
                            let ids = (row["saved_matches"] as! [[String:Any]]).map { $0["id"] as! String }
                            precondition(ids == value as! [String], "\(name): saved match order")
                        } else {
                            precondition((row[key] as? String) == (value as? String), "\(name): \(key) got \(String(describing: row[key])) expected \(value)")
                        }
                    }
                }
            }
        }
        var inspection = Inspection()
        inspection.prepareAttendees()
        let draft = CodedTranscript.extract("Attendee: Jane Smith. Equipment: Scaffold. Location: North. Action: Install pins.", library: [])
        inspection.applyTranscriptDraft(draft)
        precondition(inspection.sharedAttendees.contains { $0.name == "Jane Smith" })
        precondition(inspection.reports.first?.status == "OIs")
        precondition(inspection.reports.first?.open_items.first?.action == "Install pins")
        print("Offline transcript extraction passed \(cases.count) shared fixtures and editable-draft application.")
    }
}
