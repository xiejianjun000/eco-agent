import Vision
import AppKit
let path = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : ""
guard let img = NSImage(contentsOfFile: path), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { print("ERR_NOIMG"); exit(1) }
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.recognitionLanguages = ["zh-Hans", "en-US"]
req.usesLanguageCorrection = true
try? VNImageRequestHandler(cgImage: cg).perform([req])
let lines = (req.results as? [VNRecognizedTextObservation])?.map { $0.topCandidates(1).first?.string ?? "" } ?? []
print(lines.joined(separator: "\n"))
