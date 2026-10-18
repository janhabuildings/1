import SwiftUI
import UIKit
import AVFoundation
import Speech
import MessageUI

struct CameraView: UIViewControllerRepresentable {
    var captured: (UIImage) -> Void
    @Environment(\.dismiss) var dismiss
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController(); picker.sourceType = .camera; picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ controller: UIImagePickerController, context: Context) {}
    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraView
        init(_ parent: CameraView) { self.parent = parent }
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage { parent.captured(image) }
            parent.dismiss()
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { parent.dismiss() }
    }
}

@MainActor final class AudioCapture: NSObject, ObservableObject {
    @Published var recording = false
    @Published var transcribing = false
    private var recorder: AVAudioRecorder?
    private var task: SFSpeechRecognitionTask?
    private var continuation: CheckedContinuation<String, Error>?
    private var timer: Timer?
    private var activeURL: URL?
    func start() async throws {
        guard !recording else { return }
        let allowed = await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { continuation.resume(returning: $0) }
        }
        guard allowed else { throw APIError(message: "Microphone permission is required. Enable it in iPhone Settings.") }
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetooth])
        try session.setActive(true)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".m4a")
        let settings: [String: Any] = [AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 22050.0,
            AVNumberOfChannelsKey: 1, AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue]
        recorder = try AVAudioRecorder(url: url, settings: settings)
        guard recorder?.record() == true else { throw APIError(message: "Could not start recording.") }
        activeURL = url; recording = true
    }
    func stop() -> URL? {
        guard recording else { return nil }
        recorder?.stop(); recorder = nil; recording = false
        try? AVAudioSession.sharedInstance().setActive(false)
        let result = activeURL; activeURL = nil
        return result
    }
    func transcribe(_ url: URL) async throws -> String {
        guard !transcribing else { throw APIError(message: "Transcription is already running.") }
        let status = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0) }
        }
        guard status == .authorized, let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US")),
              recognizer.supportsOnDeviceRecognition, recognizer.isAvailable else {
            throw APIError(message: "On-device English transcription isn't available. You can type or import a transcript; audio was not sent to a cloud service.")
        }
        let request = SFSpeechURLRecognitionRequest(url: url)
        request.requiresOnDeviceRecognition = true
        transcribing = true
        defer { transcribing = false; task?.cancel(); task = nil; timer?.invalidate(); timer = nil }
        return try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<String, Error>) in
            self.continuation = continuation
            self.timer = Timer.scheduledTimer(withTimeInterval: 120, repeats: false) { [weak self] _ in
                Task { @MainActor in self?.finish(.failure(APIError(message: "Transcription timed out. Split the recording or import a transcript."))) }
            }
            self.task = recognizer.recognitionTask(with: request) { [weak self] result, error in
                Task { @MainActor in
                    if let error { self?.finish(.failure(error)) }
                    else if let result, result.isFinal { self?.finish(.success(result.bestTranscription.formattedString)) }
                }
            }
        }
    }
    private func finish(_ result: Result<String, Error>) {
        guard let continuation else { return }
        self.continuation = nil; continuation.resume(with: result)
    }
}

struct ShareSheet: UIViewControllerRepresentable {
    var items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems: items, applicationActivities: nil) }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
struct MailDraft: UIViewControllerRepresentable {
    var subject: String
    var html: String
    var attachments: [MailAttachment]
    @Environment(\.dismiss) var dismiss
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIViewController(context: Context) -> MFMailComposeViewController {
        let controller = MFMailComposeViewController(); controller.mailComposeDelegate = context.coordinator
        controller.setSubject(subject); controller.setMessageBody(html, isHTML: true)
        for attachment in attachments {
            controller.addAttachmentData(attachment.data, mimeType: "application/pdf", fileName: attachment.filename)
        }
        return controller
    }
    func updateUIViewController(_ controller: MFMailComposeViewController, context: Context) {}
    final class Coordinator: NSObject, MFMailComposeViewControllerDelegate {
        let parent: MailDraft
        init(_ parent: MailDraft) { self.parent = parent }
        func mailComposeController(_ controller: MFMailComposeViewController, didFinishWith result: MFMailComposeResult, error: Error?) { parent.dismiss() }
    }
}
struct TextDraft: UIViewControllerRepresentable {
    var body: String
    @Environment(\.dismiss) var dismiss
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIViewController(context: Context) -> MFMessageComposeViewController {
        let controller = MFMessageComposeViewController(); controller.body = body; controller.messageComposeDelegate = context.coordinator
        return controller
    }
    func updateUIViewController(_ controller: MFMessageComposeViewController, context: Context) {}
    final class Coordinator: NSObject, MFMessageComposeViewControllerDelegate {
        let parent: TextDraft
        init(_ parent: TextDraft) { self.parent = parent }
        func messageComposeViewController(_ controller: MFMessageComposeViewController, didFinishWith result: MessageComposeResult) { parent.dismiss() }
    }
}
