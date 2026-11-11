import SwiftUI
import UIKit
import AVFoundation
import Speech
import MessageUI

// Capture directly into the inspection; no system Retake / Use Photo review.
struct CameraView: View {
    var captured: (UIImage) -> Void
    var recorded: (URL) -> Void
    var closed: () -> Void
    @StateObject private var capture = InspectionCamera()
    @State private var videoMode = false
    @Environment(\.scenePhase) private var phase
    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            CameraPreview(session: capture.session).ignoresSafeArea()
            VStack {
                HStack {
                    Button("Back to inspection", action: closed).disabled(capture.recording || capture.capturing)
                    Spacer()
                    if capture.recording { Label("Recording with sound", systemImage: "record.circle.fill").foregroundStyle(.red) }
                }.padding().background(.black.opacity(0.65))
                Spacer()
                if !capture.message.isEmpty { Text(capture.message).padding().background(.black.opacity(0.7)) }
                Picker("Capture mode", selection: $videoMode) { Text("Photo").tag(false); Text("Video + voice").tag(true) }
                    .pickerStyle(.segmented).padding().disabled(capture.recording || capture.capturing)
                Button {
                    if videoMode { capture.toggleVideo() } else { capture.takePhoto() }
                } label: {
                    Image(systemName: capture.recording ? "stop.circle.fill" : videoMode ? "record.circle" : "camera.circle.fill")
                        .font(.system(size: 72)).foregroundStyle(videoMode ? .red : .white)
                }.accessibilityLabel(capture.recording ? "Stop video recording" : videoMode ? "Record video with voice" : "Take photo")
                    .disabled(!capture.ready || capture.capturing)
                Text("Videos stop at 39 MB. Inform participants before recording voice.").font(.caption).padding(.bottom)
            }.foregroundStyle(.white)
        }.onAppear { capture.start(photo: captured, video: recorded) }.onDisappear { capture.stop() }
            .onChange(of: phase) { _, value in if value == .active { capture.resume() } else { capture.stop() } }
    }
}
private final class InspectionCamera: NSObject, ObservableObject, AVCapturePhotoCaptureDelegate, AVCaptureFileOutputRecordingDelegate {
    let session = AVCaptureSession()
    private let queue = DispatchQueue(label: "jbi.inspection.camera")
    private let photos = AVCapturePhotoOutput()
    private let movies = AVCaptureMovieFileOutput()
    private var photoHandler: ((UIImage) -> Void)?
    private var videoHandler: ((URL) -> Void)?
    private var audioAdded = false
    @Published var ready = false
    @Published var recording = false
    @Published var capturing = false
    @Published var message = ""
    func start(photo: @escaping (UIImage) -> Void, video: @escaping (URL) -> Void) {
        photoHandler = photo; videoHandler = video
        queue.async {
            do {
                self.session.beginConfiguration()
                self.session.sessionPreset = .hd1280x720
                guard let camera = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back) else { throw APIError(message: "No camera is available.") }
                let input = try AVCaptureDeviceInput(device: camera)
                guard self.session.canAddInput(input), self.session.canAddOutput(self.photos), self.session.canAddOutput(self.movies) else { throw APIError(message: "Photo/video capture is unavailable on this device.") }
                self.session.addInput(input); self.session.addOutput(self.photos); self.session.addOutput(self.movies)
                self.movies.maxRecordedFileSize = 39 * 1024 * 1024
                self.session.commitConfiguration(); self.session.startRunning()
                DispatchQueue.main.async { self.ready = true }
            } catch {
                self.session.commitConfiguration()
                DispatchQueue.main.async { self.message = error.localizedDescription }
            }
        }
    }
    func resume() {
        queue.async {
            guard !self.session.inputs.isEmpty else { return }
            if !self.session.isRunning { self.session.startRunning() }
            DispatchQueue.main.async { self.ready = true }
        }
    }
    func stop() {
        DispatchQueue.main.async { self.ready = false }
        queue.async {
            if self.movies.isRecording { self.movies.stopRecording() }
            if self.session.isRunning { self.session.stopRunning() }
        }
    }
    func takePhoto() {
        guard ready, !capturing, !recording else { return }
        capturing = true
        let settings = AVCapturePhotoSettings()
        photos.capturePhoto(with: settings, delegate: self)
    }
    func toggleVideo() {
        if recording { capturing = true; movies.stopRecording(); return }
        guard ready, !capturing else { return }
        capturing = true
        AVCaptureDevice.requestAccess(for: .audio) { allowed in
            guard allowed else {
                DispatchQueue.main.async { self.capturing = false; self.message = "Microphone access is required for video with voice. Enable it in iPhone Settings." }
                return
            }
            self.queue.async {
                do {
                    if !self.audioAdded {
                        guard let device = AVCaptureDevice.default(for: .audio) else { throw APIError(message: "No microphone is available.") }
                        let input = try AVCaptureDeviceInput(device: device)
                        self.session.beginConfiguration()
                        guard self.session.canAddInput(input) else { self.session.commitConfiguration(); throw APIError(message: "Microphone is in use. Stop other recordings before capturing video.") }
                        self.session.addInput(input); self.audioAdded = true; self.session.commitConfiguration()
                    }
                    let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".mov")
                    self.movies.startRecording(to: url, recordingDelegate: self)
                } catch { DispatchQueue.main.async { self.capturing = false; self.message = error.localizedDescription } }
            }
        }
    }
    func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        DispatchQueue.main.async {
            self.capturing = false
            if let error { self.message = error.localizedDescription; return }
            guard let bytes = photo.fileDataRepresentation(), let image = UIImage(data: bytes) else { self.message = "Could not read the captured photo."; return }
            self.photoHandler?(image)
        }
    }
    func fileOutput(_ output: AVCaptureFileOutput, didStartRecordingTo fileURL: URL, from connections: [AVCaptureConnection]) {
        DispatchQueue.main.async { self.recording = true; self.capturing = false; self.message = "" }
    }
    func fileOutput(_ output: AVCaptureFileOutput, didFinishRecordingTo outputFileURL: URL, from connections: [AVCaptureConnection], error: Error?) {
        DispatchQueue.main.async {
            self.recording = false; self.capturing = false
            if let error = error as NSError?, (error.userInfo[AVErrorRecordingSuccessfullyFinishedKey] as? Bool) != true {
                self.message = error.localizedDescription; try? FileManager.default.removeItem(at: outputFileURL); return
            }
            self.videoHandler?(outputFileURL)
        }
    }
}
private final class CameraPreviewUIView: UIView {
    override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
    var preview: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
}
private struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession
    func makeUIView(context: Context) -> CameraPreviewUIView {
        let view = CameraPreviewUIView(); view.preview.session = session; view.preview.videoGravity = .resizeAspectFill
        return view
    }
    func updateUIView(_ view: CameraPreviewUIView, context: Context) {}
}

@MainActor final class AudioCapture: NSObject, ObservableObject {
    @Published var recording = false
    @Published var transcribing = false
    private var recorder: AVAudioRecorder?
    private var task: SFSpeechRecognitionTask?
    private var continuation: CheckedContinuation<String, Error>?
    private var timer: Timer?
    private var activeURL: URL?
    private var recognizer: SFSpeechRecognizer?
    private var recognitionID = UUID()
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
    func transcribe(_ url: URL, allowNetwork: Bool = false) async throws -> String {
        guard !transcribing else { throw APIError(message: "Transcription is already running.") }
        guard !recording else { throw APIError(message: "Stop the recording before transcribing it.") }
        guard FileManager.default.fileExists(atPath: url.path) else { throw APIError(message: "The recording is not available on this phone. Refresh the inspection to download it.") }
        transcribing = true
        defer { transcribing = false; task?.cancel(); task = nil; recognizer = nil; timer?.invalidate(); timer = nil }
        let status = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0) }
        }
        guard status == .authorized else { throw APIError(message: "Speech recognition permission is required. Enable Speech Recognition for JBI Inspections in iPhone Settings → Privacy & Security.") }
        guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US")), recognizer.isAvailable else { throw APIError(message: "English speech recognition is unavailable. Check the phone language, Dictation settings and internet connection, then retry.") }
        guard allowNetwork || recognizer.supportsOnDeviceRecognition else { throw APIError(message: "On-device English recognition is unavailable on this phone. Download the English Dictation language in Settings, or choose Allow Apple speech service when transcribing this recording.") }
        let identity = UUID(); recognitionID = identity
        self.recognizer = recognizer
        let request = SFSpeechURLRecognitionRequest(url: url)
        request.requiresOnDeviceRecognition = !allowNetwork
        request.shouldReportPartialResults = false
        request.taskHint = .dictation
        return try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<String, Error>) in
            self.continuation = continuation
            self.timer = Timer.scheduledTimer(withTimeInterval: 120, repeats: false) { [weak self] _ in
                Task { @MainActor in guard self?.recognitionID == identity else { return }; self?.finish(.failure(APIError(message: "Transcription timed out. Split the recording or import a transcript."))) }
            }
            self.task = recognizer.recognitionTask(with: request) { [weak self] result, error in
                Task { @MainActor in
                    guard self?.recognitionID == identity else { return }
                    if let result, result.isFinal {
                        let text = result.bestTranscription.formattedString.trimmingCharacters(in: .whitespacesAndNewlines)
                        self?.finish(text.isEmpty ? .failure(APIError(message: "No speech was detected in this recording. Check its playback volume and try a shorter clip.")) : .success(text))
                    } else if let error { self?.finish(.failure(APIError(message: error.localizedDescription + (allowNetwork ? " Check internet access or try a shorter recording." : " Try a shorter clip or explicitly allow Apple speech service.")))) }
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
    var sender: String
    var to: [String]
    var cc: [String]
    @Environment(\.dismiss) var dismiss
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIViewController(context: Context) -> MFMailComposeViewController {
        let controller = MFMailComposeViewController(); controller.mailComposeDelegate = context.coordinator
        controller.setSubject(subject); controller.setMessageBody(html, isHTML: true)
        if !sender.isEmpty { controller.setPreferredSendingEmailAddress(sender) }
        controller.setToRecipients(to); controller.setCcRecipients(cc)
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
