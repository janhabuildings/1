import Foundation

@main struct CalendarRegression {
    static func main() throws {
        let data = try Data(contentsOf: URL(fileURLWithPath: "ios/Tests/calendar-response.json"))
        let candidates = try JSONDecoder().decode(CalendarCandidates.self, from: data)
        var inspection = Inspection()
        candidates.apply(to: &inspection, applyDates: true)
        precondition(inspection.client == "Keltech")
        precondition(inspection.request_date == "2026-10-16")
        precondition(inspection.inspection_date == "2026-10-22")
        precondition(inspection.reports.count == 1 && inspection.reports[0].equipment == "OT")
        precondition(inspection.reports[0].client == "Keltech")
        precondition(inspection.reports[0].status.isEmpty && inspection.reports[0].attendees.count == 3)
        precondition(inspection.reports[0].drawings_approved.isEmpty)
        let titles = candidates.titles!
        candidates.apply(to: &inspection, selectedTitle: titles[0])
        precondition(inspection.reports[0].inspection_code == "V")
        precondition(inspection.reports[0].site["other_name"] == "Main Building Interior Shoring")
        candidates.apply(to: &inspection, selectedTitle: titles[2], previousTitle: titles[0])
        precondition(inspection.reports[0].inspection_code == "VI")
        precondition(inspection.reports[0].site["other_name"] == "Field House Interior Shoring")
        inspection.reports[0].inspection_code = "MANUAL"
        inspection.reports[0].address = "Reviewed address"
        candidates.apply(to: &inspection, selectedTitle: titles[0], previousTitle: titles[2])
        precondition(inspection.reports[0].inspection_code == "MANUAL")
        precondition(inspection.reports[0].address == "Reviewed address")
        let reopened = try JSONDecoder().decode(Inspection.self, from: JSONEncoder().encode(inspection))
        precondition(reopened.calendar_candidates == candidates && reopened.client == "Keltech")

        // Extraction before choosing an equipment type must survive reopening.
        let common = CalendarCandidates(fields: ["client": "Contractor", "address": "Site", "request_date": "2026-10-16"], equipment: [])
        var blank = Inspection()
        common.apply(to: &blank, applyDates: true)
        precondition(blank.reports.isEmpty && blank.client == "Contractor")
        blank = try JSONDecoder().decode(Inspection.self, from: JSONEncoder().encode(blank))
        var report = ReportDraft(equipment: "SF")
        blank.calendar_candidates!.fill(&report, inspection: blank)
        precondition(report.client == "Contractor" && report.address == "Site" && report.request_date == "2026-10-16")
        precondition(report.status.isEmpty && report.permit.isEmpty)
        // Old app caches have none of the new optional properties.
        var old = try JSONSerialization.jsonObject(with: JSONEncoder().encode(Inspection())) as! [String: Any]
        for key in ["client", "request_date", "requested_by", "address", "subject_project", "calendar_candidates"] { old.removeValue(forKey: key) }
        _ = try JSONDecoder().decode(Inspection.self, from: JSONSerialization.data(withJSONObject: old))
        var attendeeInspection = Inspection()
        attendeeInspection.client = "Calendar Contractor"
        attendeeInspection.prepareAttendees()
        precondition(attendeeInspection.sharedAttendees.count == 3)
        precondition(attendeeInspection.sharedAttendees[0].company == "Calendar Contractor")
        precondition(attendeeInspection.sharedAttendees[0].title == "Competent Person/Site Supervisor")
        precondition(attendeeInspection.sharedAttendees[1].company == "NYC SCA")
        attendeeInspection.insertAttendee(Attendee(name: "Added Person", company: "Contractor", title: "Competent Person"))
        precondition(attendeeInspection.sharedAttendees[2].name == "Added Person")
        precondition(attendeeInspection.sharedAttendees.last?.name == "Kamruz Zaman")
        attendeeInspection.reports = [ReportDraft(equipment: "SF"), ReportDraft(equipment: "SH")]
        attendeeInspection.prepareAttendees()
        precondition(attendeeInspection.reports.allSatisfy { $0.attendees == attendeeInspection.sharedAttendees })
        attendeeInspection.sharedAttendees = []
        attendeeInspection.prepareAttendees()
        precondition(attendeeInspection.sharedAttendees.isEmpty) // explicit removal survives reopening
        var legacy = Inspection()
        let firstPerson = Attendee(name: "First report person", company: "Client", title: "Competent Person")
        let secondPerson = Attendee(name: "Second report person", company: "NYC SCA", title: "Safety Inspector")
        legacy.attendees = [firstPerson]
        var firstReport = ReportDraft(equipment: "SF"); firstReport.attendees = [firstPerson]
        var secondReport = ReportDraft(equipment: "SH"); secondReport.attendees = [secondPerson]
        legacy.reports = [firstReport, secondReport]; legacy.prepareAttendees()
        precondition(legacy.sharedAttendees.count == 2)
        precondition(legacy.reports.allSatisfy { $0.attendees == legacy.sharedAttendees })
        var selected = Inspection()
        candidates.apply(to: &selected)
        precondition(selected.reports[0].status.isEmpty)
        selected.confirmCalendarTitle(titles[0], candidates: candidates)
        precondition(selected.reports[0].status == "OIs")
        selected.confirmCalendarTitle(titles[1], candidates: candidates)
        precondition(selected.reports[0].status == "No OIs")
        print("Calendar extraction, selection, manual edits, reopen and legacy-cache regression checks passed.")
    }
}
